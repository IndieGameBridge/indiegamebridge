"""Rebuild the GenreStats read model behind the Genre Trends page, in one pass.

Two queries over the last 4 weeks' approved streams, each one read of the streams table:
  - streams and distinct streamers per genre and language, from each stream's genre_ids;
  - hours per genre and language: each stream's duration is split evenly over its
    snapshots, each snapshot's share is summed for the game it saw, and each game's sum
    goes to its genres, so time in a category with no genres, such as Just Chatting,
    counts for none.
Then the table's rows are replaced in one transaction. Meant for cron once a day, before
update_cached_pages rebuilds the page, which is all that reads them.
"""

from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.jobs.recording import RecordedCommand
from apps.streams.languages import LANGUAGE_NAMES
from apps.streams.models import GameGenre, GenreStats

# Fixed window: stats summarise the last 4 weeks, matching search/distribution.
WINDOW_DAYS = 28

STREAMS_SQL = """
    SELECT genre_id, stream.language, count(*), count(DISTINCT stream.streamer_profile_id)
    FROM streams_stream AS stream, unnest(stream.genre_ids) AS genre_id
    WHERE stream.status = 'approved' AND stream.finished_at >= %s AND stream.language = ANY(%s)
    GROUP BY genre_id, stream.language
"""

# Snapshots keep the game as "g", a number; it's matched as text, so an odd value
# matches no game rather than failing the cast.
#
# OFFSET 0 keeps the inner query apart, so the sum per game is handed each stream's
# language, duration, snapshot count and game ids, not the whole row with its snapshots.
# Over whole rows, the 4 weeks' tens of millions of snapshots spilled tens of gigabytes to
# temp files, which filled the VPS's disk (the 2026-11-03 run). Summed per game first,
# what's left to spread over genres is a few tens of thousands of rows.
HOURS_SQL = """
    WITH game_seconds AS (
        SELECT game_id, stream.language, sum(stream.duration::float8 / stream.snapshot_count) AS seconds
        FROM (
            SELECT language, duration, jsonb_array_length(snapshots) AS snapshot_count,
                   jsonb_path_query_array(snapshots, '$[*].g') AS game_ids
            FROM streams_stream
            WHERE status = 'approved' AND finished_at >= %s AND language = ANY(%s)
              AND jsonb_typeof(snapshots) = 'array' AND duration > 0
            OFFSET 0
        ) AS stream
        CROSS JOIN LATERAL jsonb_array_elements_text(stream.game_ids) AS game_id
        GROUP BY game_id, stream.language
    )
    SELECT genre.host_genre_id, game_seconds.language, sum(game_seconds.seconds)
    FROM game_seconds
    JOIN streams_game AS game ON game.host_game_id::text = game_seconds.game_id
    JOIN streams_game_genres AS link ON link.game_id = game.id
    JOIN streams_gamegenre AS genre ON genre.id = link.gamegenre_id
    GROUP BY genre.host_genre_id, game_seconds.language
"""


class Command(RecordedCommand):
    help = (
        "Recompute per-genre stats for the Genre Trends page from the approved streams of the"
        f" last {WINDOW_DAYS} days, in one pass, for every language collected."
    )

    def handle(self, *args, **options):
        window_start = timezone.now() - timedelta(days=WINDOW_DAYS)
        params = [window_start, list(LANGUAGE_NAMES)]
        with connection.cursor() as cur:
            cur.execute(STREAMS_SQL, params)
            counts = {(genre_id, language): (streams, streamers) for genre_id, language, streams, streamers in cur.fetchall()}
            cur.execute(HOURS_SQL, params)
            seconds = {(genre_id, language): total for genre_id, language, total in cur.fetchall()}

        genre_pks = dict(GameGenre.objects.values_list("host_genre_id", "id"))
        now = timezone.now()
        rows = [
            GenreStats(
                genre_id=genre_pks[host_genre_id],
                language=language,
                streams_count=counts.get((host_genre_id, language), (0, 0))[0],
                streamers_count=counts.get((host_genre_id, language), (0, 0))[1],
                total_duration_seconds=round(seconds.get((host_genre_id, language), 0)),
                computed_at=now,
            )
            for host_genre_id, language in sorted(set(counts) | set(seconds))
            # A stream may carry a genre id the genre table doesn't know; it's no genre to show.
            if host_genre_id in genre_pks
        ]
        with transaction.atomic():
            GenreStats.objects.all().delete()
            GenreStats.objects.bulk_create(rows)
        self.count(rows=len(rows))
        self.stdout.write(f"Rebuilt the genre stats: {len(rows):,} genre and language rows.")
