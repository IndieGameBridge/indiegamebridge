"""Rebuild the per-game public pages, /game/<slug>, in one pass.

One read of the last 4 weeks' approved streams counts, for every game, its streams and its
different streamers, in each page language and each week, as the search counts them. The
streamers' sizes come from the search table; the hours of play, and of the day, from
GameStats. A game that PAGE_MIN_STREAMERS different streamers played gets a page, with an
address made from its name, and keeps it: then every page's numbers are rewritten, down to zero
for a game nobody streamed lately, whose page stays where it is. Meant for cron every 6 hours,
2 hours after rebuild_game_stats, whose hours it reads.
"""

from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.jobs.recording import RecordedCommand
from apps.streams.game_pages import (
    ALSO_PLAYED_COUNT,
    ALSO_PLAYED_FULL_WEIGHT,
    ALSO_PLAYED_MIN_LIFT,
    ALSO_PLAYED_MIN_SHARED,
    BASELINES_CACHE_KEY,
    DETAIL_MIN_STREAMERS,
    INDIE_GENRE_ID,
    PAGE_MIN_STREAMERS,
    display_name,
    new_slug,
    shared_names,
)
from apps.streams.languages import ALL_LANGUAGES, PAGE_LANGUAGES
from apps.streams.models import Game, GamePage, GameStats, JsonCache
from apps.streams.size_groups import PEAK_THRESHOLDS, SIZE_GROUPS

# The window, as the search's: streams that ended in the last 4 weeks.
WINDOW_DAYS = 28

# One row per (game, streamer, language): their streams of it, the seconds played, when the
# newest ended, and the weeks they played it in, as bits, 1 for the newest week. A stream counts
# for every game it played, and only the categories IGDB lists as games count. Its length is
# split evenly between all the categories it played, Just Chatting and the like included.
PAIRS_SQL = """
    CREATE TEMP TABLE game_page_pairs AS
    SELECT game.id AS game_id, stream.streamer_profile_id AS streamer_id, stream.language,
           count(*)::int AS streams,
           sum(stream.duration::float8 / greatest(cardinality(stream.host_game_ids), 1)) AS seconds,
           max(stream.finished_at) AS last_streamed_at,
           bit_or(1 << least(3, floor(extract(epoch FROM (%(end)s - stream.finished_at)) / 604800)::int)) AS weeks
    FROM streams_stream AS stream
    CROSS JOIN LATERAL unnest(stream.host_game_ids) AS played(host_game_id)
    JOIN streams_game AS game ON game.host_game_id = played.host_game_id AND game.category = 'isgame'
    WHERE stream.status = 'approved' AND stream.finished_at >= %(start)s AND stream.language = ANY(%(languages)s)
    GROUP BY 1, 2, 3
"""

# The same per (game, streamer), whatever the language: who played what.
STREAMERS_SQL = """
    CREATE TEMP TABLE game_page_streamers AS
    SELECT game_id, streamer_id, bit_or(weeks) AS weeks
    FROM game_page_pairs
    GROUP BY 1, 2
"""

# Every game's streamers, its streamers in each week (newest first), its streams, hours played
# and when the newest ended.
TOTALS_SQL = """
    SELECT players.game_id, players.streamers, players.week0, players.week1, players.week2, players.week3,
           streams.streams, streams.hours, streams.last_streamed_at
    FROM (
        SELECT game_id, count(*) AS streamers,
               count(*) FILTER (WHERE weeks & 1 <> 0) AS week0, count(*) FILTER (WHERE weeks & 2 <> 0) AS week1,
               count(*) FILTER (WHERE weeks & 4 <> 0) AS week2, count(*) FILTER (WHERE weeks & 8 <> 0) AS week3
        FROM game_page_streamers
        GROUP BY game_id
    ) AS players
    JOIN (
        SELECT game_id, sum(streams)::int AS streams, round(sum(seconds) / 3600)::int AS hours,
               max(last_streamed_at) AS last_streamed_at
        FROM game_page_pairs
        GROUP BY game_id
    ) AS streams USING (game_id)
"""

# The games with pages: their streams and streamers in each language, and their streamers by size.
LANGUAGES_SQL = """
    SELECT pairs.game_id, pairs.language, sum(pairs.streams)::int, count(*)
    FROM game_page_pairs AS pairs
    JOIN streams_gamepage AS page ON page.game_id = pairs.game_id
    GROUP BY 1, 2
"""

# width_bucket gives each peak its index in SIZE_GROUPS. A streamer the search table doesn't
# know yet has no size and is left out.
SIZES_SQL = """
    SELECT pairs.game_id, width_bucket(stats.peak_viewers, %(group_starts)s::int[]), count(*)
    FROM game_page_pairs AS pairs
    JOIN streams_gamepage AS page ON page.game_id = pairs.game_id
    JOIN streams_streamersearchstats AS stats
        ON stats.streamer_profile_id = pairs.streamer_id AND stats.language = pairs.language
    GROUP BY 1, 2
"""

# When it's played: each hour of the day, UTC, from GameStats, every page language added up and
# any size, each stream counting once in each hour it was seen on the game. Only the hours'
# shares are shown, so the clock hours a stream only touched don't matter.
HOURS_SQL = """
    SELECT stats.game_id, cell.hour %% 24, sum(cell.streams)::int
    FROM streams_gamestats AS stats
    JOIN streams_gamepage AS page ON page.game_id = stats.game_id
    CROSS JOIN LATERAL unnest(stats.hours, stats.streams) AS cell(hour, streams)
    WHERE stats.language = %(all_languages)s AND stats.size_group = %(any_size)s
    GROUP BY 1, 2
"""

# The games each page game's streamers played far more often than streamers in general:
# (streamers who played both / its streamers) against (the other game's streamers / all
# streamers). Both games have pages, so each can link to the other. Two categories of one game -
# the same IGDB id, or names alike but for case and punctuation - aren't each other's.
ALSO_PLAYED_SQL = """
    WITH page_games AS (
        SELECT streamers.game_id, count(*) AS players
        FROM game_page_streamers AS streamers
        JOIN streams_gamepage AS page ON page.game_id = streamers.game_id
        GROUP BY streamers.game_id
    ),
    page_pairs AS (
        SELECT streamers.game_id, streamers.streamer_id
        FROM game_page_streamers AS streamers
        JOIN page_games USING (game_id)
    ),
    shared AS (
        SELECT one.game_id AS game_id, other.game_id AS other_id, count(*) AS together
        FROM page_pairs AS one
        JOIN page_pairs AS other ON other.streamer_id = one.streamer_id AND other.game_id <> one.game_id
        GROUP BY 1, 2
        HAVING count(*) >= %(min_shared)s
    ),
    scored AS (
        SELECT shared.game_id, shared.other_id, shared.together,
               (shared.together::float8 / one.players) / (other.players::float8 / %(all_streamers)s) AS lift
        FROM shared
        JOIN page_games AS one ON one.game_id = shared.game_id
        JOIN page_games AS other ON other.game_id = shared.other_id
        JOIN streams_game AS one_game ON one_game.id = shared.game_id
        JOIN streams_game AS other_game ON other_game.id = shared.other_id
        WHERE one_game.igdb_game_id <> other_game.igdb_game_id
          AND NOT (
              regexp_replace(lower(one_game.host_name), '[^a-z0-9]', '', 'g') <> ''
              AND regexp_replace(lower(one_game.host_name), '[^a-z0-9]', '', 'g')
                  = regexp_replace(lower(other_game.host_name), '[^a-z0-9]', '', 'g')
          )
    ),
    ranked AS (
        SELECT game_id, other_id, together, lift,
               row_number() OVER (
                   PARTITION BY game_id
                   ORDER BY lift * least(1.0, together / %(full_weight)s::float8) DESC, other_id
               ) AS place
        FROM scored
        WHERE lift >= %(min_lift)s
    )
    SELECT game_id, other_id, together, lift FROM ranked WHERE place <= %(count)s ORDER BY game_id, place
"""

# The baselines: the streams in each language, and the streamers of each size, of every game
# and of indie games. Streams are counted as on a game's page, once for each game they played.
INDIE_GAMES_CTE = """
    indie AS (
        SELECT link.game_id
        FROM streams_game_genres AS link
        JOIN streams_gamegenre AS genre ON genre.id = link.gamegenre_id
        WHERE genre.host_genre_id = %(indie)s
    )
"""

BASE_LANGUAGES_SQL = f"""
    WITH {INDIE_GAMES_CTE}
    SELECT pairs.language, sum(pairs.streams)::int, coalesce(sum(pairs.streams) FILTER (WHERE indie.game_id IS NOT NULL), 0)::int
    FROM game_page_pairs AS pairs
    LEFT JOIN indie USING (game_id)
    GROUP BY 1
"""

BASE_SIZES_SQL = f"""
    WITH {INDIE_GAMES_CTE},
    players AS (
        SELECT pairs.streamer_id, pairs.language, bool_or(indie.game_id IS NOT NULL) AS indie
        FROM game_page_pairs AS pairs
        LEFT JOIN indie USING (game_id)
        GROUP BY 1, 2
    )
    SELECT width_bucket(stats.peak_viewers, %(group_starts)s::int[]), count(*), count(*) FILTER (WHERE players.indie)
    FROM players
    JOIN streams_streamersearchstats AS stats
        ON stats.streamer_profile_id = players.streamer_id AND stats.language = players.language
    GROUP BY 1
"""


class Command(RecordedCommand):
    help = (
        "Recompute the per-game public pages: give a page to every game enough different streamers played in the"
        " last 4 weeks, and rewrite every page's numbers, in one pass."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        params = {
            "start": now - timedelta(days=WINDOW_DAYS),
            "end": now,
            "languages": list(PAGE_LANGUAGES),
            "group_starts": [threshold + 1 for threshold in PEAK_THRESHOLDS],
            "all_languages": ALL_LANGUAGES,
            "any_size": GameStats.ANY_SIZE,
            "indie": INDIE_GENRE_ID,
            "min_shared": ALSO_PLAYED_MIN_SHARED,
            "min_lift": ALSO_PLAYED_MIN_LIFT,
            "full_weight": ALSO_PLAYED_FULL_WEIGHT,
            "count": ALSO_PLAYED_COUNT,
        }
        with transaction.atomic(), connection.cursor() as cur:
            # At the default 4 MB the streams' pass and the also-played spill about 1.6 GB of temp
            # files; at this, about half.
            cur.execute("SET LOCAL work_mem = '64MB'")
            cur.execute(PAIRS_SQL, params)
            cur.execute(STREAMERS_SQL)
            cur.execute("ANALYZE game_page_pairs")
            cur.execute("ANALYZE game_page_streamers")

            cur.execute(TOTALS_SQL)
            totals = {row[0]: row[1:] for row in cur.fetchall()}
            created = self._create_pages(totals)

            cur.execute("SELECT count(DISTINCT streamer_id) FROM game_page_streamers")
            params["all_streamers"] = cur.fetchone()[0] or 1
            details = self._details(cur, params)
            written = self._write_pages(totals, details, now)
            self._write_baselines(cur, params, now)

            # Gone with the transaction anyway if anything above failed; dropped here so a run
            # inside a longer transaction, such as a test's, can run again.
            cur.execute("DROP TABLE game_page_streamers")
            cur.execute("DROP TABLE game_page_pairs")
        pages = GamePage.objects.count()
        self.count(pages=pages, created=created, written=written)
        self.stdout.write(f"Rebuilt the game pages: {pages:,} pages, of which {created:,} new; {written:,} changed.")

    @staticmethod
    def _create_pages(totals: dict) -> int:
        """Pages for the games that reached PAGE_MIN_STREAMERS, the most streamed first, so of two
        games with one name the bigger one gets the plain address."""
        has_page = set(GamePage.objects.values_list("game_id", flat=True))
        reached = sorted(
            (game_id for game_id, row in totals.items() if row[0] >= PAGE_MIN_STREAMERS and game_id not in has_page),
            key=lambda game_id: (-totals[game_id][0], game_id),
        )
        if not reached:
            return 0
        games = Game.objects.in_bulk(reached)
        taken = set(GamePage.objects.values_list("slug", flat=True))
        pages = []
        for game_id in reached:
            game = games[game_id]
            if not game.host_name:
                continue
            year = game.release_date.year if game.release_date else None
            slug = new_slug(game.host_name, year, game.host_game_id, taken)
            taken.add(slug)
            pages.append(GamePage(game=game, slug=slug))
        GamePage.objects.bulk_create(pages)
        return len(pages)

    @staticmethod
    def _details(cur, params: dict) -> dict:
        """Each page game's languages, sizes, hours of the day and games also played."""
        details = {}

        def of(game_id):
            return details.setdefault(game_id, {"languages": {}, "sizes": [0] * len(SIZE_GROUPS), "hours": [0] * 24})

        cur.execute(LANGUAGES_SQL)
        for game_id, language, streams, streamers in cur.fetchall():
            of(game_id)["languages"][language] = {"streams": streams, "streamers": streamers}
        cur.execute(SIZES_SQL, params)
        for game_id, index, streamers in cur.fetchall():
            of(game_id)["sizes"][index] = streamers
        cur.execute(HOURS_SQL, params)
        for game_id, hour, hours in cur.fetchall():
            of(game_id)["hours"][hour] = hours
        cur.execute(ALSO_PLAYED_SQL, params)
        also_played = cur.fetchall()
        pages = {
            page["game_id"]: page
            for page in GamePage.objects.filter(game_id__in={row[1] for row in also_played})
            .values("game_id", "slug", "game__host_name", "game__release_date")
        }
        clashing = shared_names()
        for game_id, other_id, together, lift in also_played:
            other = pages[other_id]
            of(game_id).setdefault("also_played", []).append({
                "slug": other["slug"],
                "name": display_name(
                    other["game__host_name"], other["game__release_date"], other["game__host_name"] in clashing,
                ),
                "streamers": together,
                "lift": round(lift, 1),
            })
        return details

    @staticmethod
    def _write_pages(totals: dict, details: dict, now) -> int:
        """Every page's name and numbers, written where they changed. A page nobody streamed
        lately goes to zero and keeps when it was last streamed; one with few streamers keeps
        totals only. A name another page's game shares gets the release year."""
        clashing = shared_names()
        changed = []
        for page in GamePage.objects.select_related("game"):
            name = display_name(page.game.host_name, page.game.release_date, page.game.host_name in clashing)
            row = totals.get(page.game_id)
            if row is None:
                streamers, numbers, last = 0, {}, page.last_streamed_at
            else:
                streamers, week0, week1, week2, week3, streams, hours, last = row
                more = details.get(page.game_id, {})
                hours_of_day = more.get("hours", [0] * 24)
                numbers = {"streams": streams, "hours": hours}
                if streamers >= DETAIL_MIN_STREAMERS:
                    numbers.update({
                        "languages": more.get("languages", {}),
                        "sizes": more.get("sizes", [0] * len(SIZE_GROUPS)),
                        "weeks": [week0, week1, week2, week3],
                        "hours_of_day": hours_of_day,
                        "also_played": more.get("also_played", []),
                    })
            if (page.name, page.streamers, page.numbers, page.last_streamed_at) != (name, streamers, numbers, last):
                page.name, page.streamers, page.numbers, page.last_streamed_at = name, streamers, numbers, last
                page.updated_at = now
                changed.append(page)
        GamePage.objects.bulk_update(
            changed, ["name", "streamers", "numbers", "last_streamed_at", "updated_at"], batch_size=500,
        )
        return len(changed)

    @staticmethod
    def _write_baselines(cur, params: dict, now) -> None:
        cur.execute(BASE_LANGUAGES_SQL, params)
        languages = {"all": {}, "indie": {}}
        for language, every, indie in cur.fetchall():
            languages["all"][language] = every
            languages["indie"][language] = indie
        cur.execute(BASE_SIZES_SQL, params)
        sizes = {"all": [0] * len(SIZE_GROUPS), "indie": [0] * len(SIZE_GROUPS)}
        for index, every, indie in cur.fetchall():
            sizes["all"][index] = every
            sizes["indie"][index] = indie
        JsonCache.objects.update_or_create(
            key=BASELINES_CACHE_KEY,
            defaults={"content": {
                group: {"languages": languages[group], "sizes": sizes[group]} for group in ("all", "indie")
            } | {"computed_at": now.isoformat()}},
        )
