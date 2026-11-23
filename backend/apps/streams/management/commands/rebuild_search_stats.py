"""Rebuild the StreamerSearchStats read model: every streamer's last 4 weeks, in one pass.

One read of the streams table computes every (streamer, language) row into a temporary
table. Then only the rows whose numbers changed are written, and those of streamers with
no approved stream left in the window are deleted - in one transaction, so a search sees
the old rows or the new ones, never a mix. Meant for cron every 6 hours.

Reading the streams table costs the same for one streamer as for all of them: their
streams are spread all through it. So a pass over everyone at once is far cheaper than
one in chunks, which read the whole table for each chunk.
"""

from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.jobs.recording import RecordedCommand

# Fixed search window: stats summarise each streamer's last 4 weeks.
WINDOW_DAYS = 28

# Every (streamer, language) row the window's approved streams make. avg_viewers is
# rounded as a float, half to even, as Python rounds; genre_ids is the union of the
# streams' genres, sorted; game_ids the same for the games they played, only the categories
# IGDB lists as games; active_days the UTC days they started on, as a profile's chart
# counts them, sorted; evening_window the part of the day holding most of their time.
#
# The evening windows split each stream exactly as apps.streams.evening_windows does: in
# 8-hour steps counted from 07:00 UTC, a step's number modulo 3 is its window (0 Asia &
# Oceania, 1 Europe & Africa, 2 Americas). A stream crosses one or two boundaries at most
# in a day, so this adds a row or two per stream. A tie goes to the window the pages list
# first: Americas, then Europe & Africa.
FRESH_SQL = """
    CREATE TEMP TABLE fresh_search_stats AS
    WITH window_streams AS MATERIALIZED (
        SELECT streamer_profile_id, language, max_viewers, avg_viewers, duration, genre_ids, host_game_ids,
               (started_at AT TIME ZONE 'UTC')::date - DATE '1970-01-01' AS day,
               extract(epoch FROM started_at)::bigint - 25200 AS shifted_start
        FROM streams_stream
        WHERE status = 'approved' AND finished_at >= %s
    ),
    window_parts AS (
        SELECT streamer_profile_id, language, step %% 3 AS part,
               least(shifted_start + duration, (step + 1) * 28800) - greatest(shifted_start, step * 28800) AS seconds
        FROM window_streams,
             generate_series(shifted_start / 28800, (shifted_start + duration - 1) / 28800) AS step
        WHERE duration > 0
    ),
    windows AS (
        SELECT streamer_profile_id, language,
               coalesce(sum(seconds) FILTER (WHERE part = 2), 0) AS americas,
               coalesce(sum(seconds) FILTER (WHERE part = 1), 0) AS europe,
               coalesce(sum(seconds) FILTER (WHERE part = 0), 0) AS asia
        FROM window_parts
        GROUP BY streamer_profile_id, language
    ),
    stats AS (
        SELECT streamer_profile_id, language, max(max_viewers) AS peak_viewers,
               round(avg(avg_viewers)::float8)::int AS avg_viewers, sum(duration)::int AS total_duration_seconds,
               count(*)::int AS streams_count, array_agg(DISTINCT day ORDER BY day) AS active_days
        FROM window_streams
        GROUP BY streamer_profile_id, language
    ),
    genres AS (
        SELECT streamer_profile_id, language, array_agg(DISTINCT genre_id ORDER BY genre_id) AS genre_ids
        FROM window_streams, unnest(genre_ids) AS genre_id
        GROUP BY streamer_profile_id, language
    ),
    games AS (
        SELECT streamer_profile_id, language, array_agg(DISTINCT game.host_game_id ORDER BY game.host_game_id) AS game_ids
        FROM window_streams, unnest(host_game_ids) AS played(host_game_id)
        JOIN streams_game AS game ON game.host_game_id = played.host_game_id AND game.category = 'isgame'
        GROUP BY streamer_profile_id, language
    )
    SELECT stats.*, coalesce(genres.genre_ids, '{}') AS genre_ids, coalesce(games.game_ids, '{}') AS game_ids,
           profile.host_login, profile.host_display_name,
           CASE
               WHEN coalesce(windows.americas + windows.europe + windows.asia, 0) = 0 THEN ''
               WHEN windows.americas >= windows.europe AND windows.americas >= windows.asia THEN 'americas'
               WHEN windows.europe >= windows.asia THEN 'europe'
               ELSE 'asia'
           END AS evening_window
    FROM stats
    JOIN streams_streamerprofile AS profile ON profile.id = stats.streamer_profile_id
    LEFT JOIN genres USING (streamer_profile_id, language)
    LEFT JOIN games USING (streamer_profile_id, language)
    LEFT JOIN windows USING (streamer_profile_id, language)
"""

# New rows, and rows whose numbers or names changed; the rest stay as they are.
UPSERT_SQL = """
    INSERT INTO streams_streamersearchstats AS current (
        streamer_profile_id, language, peak_viewers, avg_viewers, total_duration_seconds, streams_count,
        genre_ids, game_ids, active_days, evening_window, host_login, host_display_name, computed_at
    )
    SELECT streamer_profile_id, language, peak_viewers, avg_viewers, total_duration_seconds, streams_count,
           genre_ids, game_ids, active_days, evening_window, host_login, host_display_name, now()
    FROM fresh_search_stats
    ON CONFLICT (streamer_profile_id, language) DO UPDATE SET
        peak_viewers = EXCLUDED.peak_viewers, avg_viewers = EXCLUDED.avg_viewers,
        total_duration_seconds = EXCLUDED.total_duration_seconds, streams_count = EXCLUDED.streams_count,
        genre_ids = EXCLUDED.genre_ids, game_ids = EXCLUDED.game_ids, active_days = EXCLUDED.active_days,
        evening_window = EXCLUDED.evening_window,
        host_login = EXCLUDED.host_login, host_display_name = EXCLUDED.host_display_name,
        computed_at = EXCLUDED.computed_at
    WHERE (current.peak_viewers, current.avg_viewers, current.total_duration_seconds, current.streams_count,
           current.genre_ids, current.game_ids, current.active_days, current.evening_window, current.host_login,
           current.host_display_name)
          IS DISTINCT FROM
          (EXCLUDED.peak_viewers, EXCLUDED.avg_viewers, EXCLUDED.total_duration_seconds, EXCLUDED.streams_count,
           EXCLUDED.genre_ids, EXCLUDED.game_ids, EXCLUDED.active_days, EXCLUDED.evening_window, EXCLUDED.host_login,
           EXCLUDED.host_display_name)
"""

# Streamers with no approved stream left in the window drop out of search.
DELETE_SQL = """
    DELETE FROM streams_streamersearchstats AS current
    WHERE NOT EXISTS (
        SELECT 1 FROM fresh_search_stats AS fresh
        WHERE fresh.streamer_profile_id = current.streamer_profile_id AND fresh.language = current.language
    )
"""


class Command(RecordedCommand):
    help = (
        "Recompute the StreamerSearchStats read model from every streamer's approved streams of"
        f" the last {WINDOW_DAYS} days, in one pass, writing only the rows that changed."
    )

    def handle(self, *args, **options):
        window_start = timezone.now() - timedelta(days=WINDOW_DAYS)
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(FRESH_SQL, [window_start])
            cur.execute("SELECT count(*) FROM fresh_search_stats")
            rows = cur.fetchone()[0]
            cur.execute(UPSERT_SQL)
            written = cur.rowcount
            cur.execute(DELETE_SQL)
            deleted = cur.rowcount
            # Gone with the transaction anyway if anything above failed; dropped here so a
            # run inside a longer transaction, such as a test's, can run again.
            cur.execute("DROP TABLE fresh_search_stats")
        self.count(rows=rows, written=written, deleted=deleted)
        self.stdout.write(
            f"Rebuilt the search stats: {rows:,} rows, of which {written:,} new or changed; {deleted:,} deleted."
        )
