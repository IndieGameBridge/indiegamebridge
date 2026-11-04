"""Rebuild the GameStats read model behind the Games page, in one pass.

One read of the last 4 weeks' streams counts how many were live on each game in each hour,
per language and streamer size. Then every list - a language and a size group - is sorted
once, and the table's rows are replaced in one transaction, so a search sees the old rows or
the new ones, never a mix. Meant for cron every 6 hours, 2 hours after the search rebuild,
whose peak_viewers give the streamers' sizes.

Streams of every status count, because approval comes hours after a stream ends: approved
streams alone would leave the newest hours nearly empty. Joining to the games leaves out what
isn't one. A streamer the search table doesn't know yet has no size, and counts only under
any size.
"""

from datetime import datetime, timezone as dt_timezone

from django.db import connection, transaction
from django.utils import timezone

from apps.jobs.recording import RecordedCommand
from apps.streams.languages import ALL_LANGUAGES, PAGE_LANGUAGES
from apps.streams.models import GameStats, JsonCache
from apps.streams.size_groups import PEAK_THRESHOLDS

# The window: the last 4 weeks of whole hours.
WINDOW_HOURS = 28 * 24

# The hours a search reads with the rows, kept under this key.
GAME_STATS_CACHE_KEY = "game_stats"

# A stream counts once in each hour it was seen on a game, so DISTINCT per stream. Snapshots
# keep the game as "g", a number; it's matched as text below, so an odd value matches no game
# rather than failing a cast.
#
# OFFSET 0 keeps the inner query apart, so the streams are joined to their sizes before their
# snapshots are spread out. The window's edge isn't checked on the snapshots here: a filter on
# them turns the aggregate into a sort, three times slower with 2 GB of temp files. A stream
# that started before the window just leaves a few old hours for the next statement to drop.
CELLS_SQL = """
    CREATE TEMP TABLE game_stats_cells AS
    SELECT cell.g, stream.language, cell.hour, stream.size_group, count(*) AS streams
    FROM (
        SELECT item.language, item.snapshots,
               width_bucket(stats.peak_viewers, %(group_starts)s::int[]) + 1 AS size_group
        FROM streams_stream AS item
        LEFT JOIN streams_streamersearchstats AS stats
            ON stats.streamer_profile_id = item.streamer_profile_id AND stats.language = item.language
        WHERE item.finished_at >= %(window_start)s AND item.language = ANY(%(languages)s)
          AND jsonb_typeof(item.snapshots) = 'array'
        OFFSET 0
    ) AS stream
    CROSS JOIN LATERAL (
        SELECT DISTINCT snap.g, snap.t / 3600 AS hour
        FROM jsonb_to_recordset(stream.snapshots) AS snap(g text, t bigint)
    ) AS cell
    GROUP BY 1, 2, 3, 4
"""

# Text for the language, which the streams table keeps in two characters: "all" needs three.
LINES_SQL = """
    CREATE TEMP TABLE game_stats_lines AS
    SELECT game.id AS game_id, cells.language::text AS language, cells.size_group,
           cells.hour::int AS hour, cells.streams::int AS streams
    FROM game_stats_cells AS cells
    JOIN streams_game AS game ON game.host_game_id::text = cells.g AND game.category = 'isgame'
    WHERE cells.hour BETWEEN %(oldest_hour)s AND %(newest_hour)s
"""

ANY_SIZE_SQL = """
    INSERT INTO game_stats_lines
    SELECT game_id, language, %(any_size)s, hour, sum(streams)::int
    FROM game_stats_lines
    GROUP BY game_id, language, hour
"""

ALL_LANGUAGES_SQL = """
    INSERT INTO game_stats_lines
    SELECT game_id, %(all_languages)s, size_group, hour, sum(streams)::int
    FROM game_stats_lines
    WHERE size_group IS NOT NULL
    GROUP BY game_id, size_group, hour
"""

# The sort: the newest hour decides, and an older hour only breaks a tie. Postgres compares
# arrays element by element, so each row gets a sort key of one number per hour with streams,
# newest first, that grows with the hour and then with the streams. An hour a game has no
# number for loses to a game with one, as its 0 would, and a list that ends first loses too.
# The game's id ends the ties left: two games can match hour for hour.
#
# Rows with no size group yet are the streamers with no size: already in ANY_SIZE, so dropped.
INSERT_SQL = """
    INSERT INTO streams_gamestats (game_id, language, size_group, position, hours, streams)
    SELECT game_id, language, size_group,
           row_number() OVER (PARTITION BY language, size_group ORDER BY sort_key DESC, game_id),
           hours, streams
    FROM (
        SELECT game_id, language, size_group,
               array_agg(hour ORDER BY hour DESC) AS hours,
               array_agg(streams ORDER BY hour DESC) AS streams,
               array_agg((hour - %(oldest_hour)s) * 1048576 + streams ORDER BY hour DESC) AS sort_key
        FROM game_stats_lines
        WHERE size_group IS NOT NULL
        GROUP BY game_id, language, size_group
    ) AS line
"""


class Command(RecordedCommand):
    help = (
        "Recompute the GameStats read model: streams live in each hour of the last 4 weeks, per"
        " game, language and streamer size, in one pass."
    )

    def handle(self, *args, **options):
        # The hour in progress is left out: it holds only the polls made so far.
        newest_hour = int(timezone.now().timestamp()) // 3600 - 1
        oldest_hour = newest_hour - WINDOW_HOURS + 1
        params = {
            "group_starts": [threshold + 1 for threshold in PEAK_THRESHOLDS],
            "window_start": datetime.fromtimestamp(oldest_hour * 3600, dt_timezone.utc),
            "languages": list(PAGE_LANGUAGES),
            "oldest_hour": oldest_hour,
            "newest_hour": newest_hour,
            "any_size": GameStats.ANY_SIZE,
            "all_languages": ALL_LANGUAGES,
        }
        with transaction.atomic(), connection.cursor() as cur:
            # At the default 4 MB the first statement spills 6 GB of temp files, at this 1 GB.
            cur.execute("SET LOCAL work_mem = '64MB'")
            cur.execute(CELLS_SQL, params)
            cur.execute(LINES_SQL, params)
            cur.execute("DROP TABLE game_stats_cells")
            cur.execute(ANY_SIZE_SQL, params)
            cur.execute(ALL_LANGUAGES_SQL, params)
            cur.execute("DELETE FROM streams_gamestats")
            cur.execute(INSERT_SQL, params)
            rows = cur.rowcount
            # Gone with the transaction anyway if anything above failed; dropped here so a
            # run inside a longer transaction, such as a test's, can run again.
            cur.execute("DROP TABLE game_stats_lines")
            JsonCache.objects.update_or_create(
                key=GAME_STATS_CACHE_KEY,
                defaults={"content": {"newest_hour": newest_hour}},
            )
        self.count(rows=rows)
        self.stdout.write(f"Rebuilt the game stats: {rows:,} rows.")
