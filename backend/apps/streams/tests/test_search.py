"""Tests for StreamerSearch._run_query filtering, ordering, and aggregates.

Each result row is one streamer aggregating only the streams that matched the
filters: streams_count, total_duration, peak_viewers, avg_viewers, and the
de-duped list of game names played. Calls _run_query directly with an
already-normalized filter dict to bypass the SearchCache and query-param
normalization.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.utils import timezone

from apps.streams.models import Game, Stream, StreamerProfile
from apps.streams.search import StreamerSearch


class RunQueryTests(TestCase):
    def _make_streamer(self, host_user_id, login):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _make_stream(self, profile, host_stream_id, max_viewers, avg_viewers, duration, host_game_ids=None):
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=host_stream_id,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=1),
            snapshots=[],
            max_viewers=max_viewers,
            avg_viewers=avg_viewers,
            duration=duration,
            host_game_ids=host_game_ids or [],
        )

    @staticmethod
    def _base_filters(**overrides):
        # Minimal normalized filter dict _run_query needs; overrides add filters.
        return {"window": 7, "lang": "en", **overrides}

    def _logins(self, results):
        return [row["login"] for row in results]

    def test_avgmin_excludes_streams_below_threshold(self):
        low = self._make_streamer(1, "low")
        high = self._make_streamer(2, "high")
        self._make_stream(low, 1, max_viewers=100, avg_viewers=3, duration=600)
        self._make_stream(high, 2, max_viewers=100, avg_viewers=50, duration=600)

        results = StreamerSearch._run_query(self._base_filters(avgmin=5))

        self.assertEqual(self._logins(results), ["high"])

    def test_avgmax_excludes_streams_above_threshold(self):
        low = self._make_streamer(1, "low")
        high = self._make_streamer(2, "high")
        self._make_stream(low, 1, max_viewers=100, avg_viewers=20, duration=600)
        self._make_stream(high, 2, max_viewers=100, avg_viewers=500, duration=600)

        results = StreamerSearch._run_query(self._base_filters(avgmax=100))

        self.assertEqual(self._logins(results), ["low"])

    def test_sort_peak_then_avg_then_duration(self):
        """Order is: peak viewers desc, then avg viewers desc, then total duration desc."""
        top_peak = self._make_streamer(1, "toppeak")
        avg_hi = self._make_streamer(2, "avghi")
        avg_lo = self._make_streamer(3, "avglo")
        dur_hi = self._make_streamer(4, "durhi")

        # Highest peak wins outright regardless of avg/duration.
        self._make_stream(top_peak, 1, max_viewers=200, avg_viewers=1, duration=1)
        # Same peak as avg_lo and dur_hi; higher avg ranks above both.
        self._make_stream(avg_hi, 2, max_viewers=100, avg_viewers=90, duration=10)
        # Same peak + same avg as dur_hi; shorter total duration ranks below it.
        self._make_stream(avg_lo, 3, max_viewers=100, avg_viewers=50, duration=9000)
        self._make_stream(dur_hi, 4, max_viewers=100, avg_viewers=90, duration=8000)

        results = StreamerSearch._run_query(self._base_filters())

        self.assertEqual(
            self._logins(results),
            ["toppeak", "durhi", "avghi", "avglo"],
        )

    def test_streamer_row_aggregates_matching_streams(self):
        """One row per streamer: stream count, summed duration, peak, mean avg,
        and the de-duped list of game names across the matched streams."""
        Game.objects.create(host_game_id=10, host_name="Alpha")
        Game.objects.create(host_game_id=20, host_name="Beta")
        Game.objects.create(host_game_id=30, host_name="Gamma")

        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, max_viewers=100, avg_viewers=40, duration=3600, host_game_ids=[10, 20])
        self._make_stream(streamer, 2, max_viewers=150, avg_viewers=80, duration=7200, host_game_ids=[20, 30])

        (row,) = StreamerSearch._run_query(self._base_filters())

        self.assertEqual(row["streams_count"], 2)
        self.assertEqual(row["peak_viewers"], 150)
        # mean of per-stream avgs: (40 + 80) / 2 = 60
        self.assertEqual(row["avg_viewers"], 60)
        # 3600 + 7200 = 10800s
        self.assertEqual(row["total_duration"], "3 h 0 min")
        # Game 20 appears in both streams but is listed once; sorted by name.
        self.assertEqual(row["games"], ["Alpha", "Beta", "Gamma"])
        # The per-stream list is gone from the payload.
        self.assertNotIn("streams", row)

    def test_unknown_game_id_falls_back_to_na(self):
        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, max_viewers=100, avg_viewers=40, duration=600, host_game_ids=[999])

        (row,) = StreamerSearch._run_query(self._base_filters())

        self.assertEqual(row["games"], ["N/A"])

    def test_only_filtered_streams_contribute_to_aggregates(self):
        """A stream excluded by a filter must not inflate the streamer's
        count/duration/peak."""
        streamer = self._make_streamer(1, "solo")
        # Kept: avg 50 >= avgmin 5.
        self._make_stream(streamer, 1, max_viewers=80, avg_viewers=50, duration=600)
        # Dropped: avg 2 < avgmin 5.
        self._make_stream(streamer, 2, max_viewers=500, avg_viewers=2, duration=9999)

        (row,) = StreamerSearch._run_query(self._base_filters(avgmin=5))

        self.assertEqual(row["streams_count"], 1)
        self.assertEqual(row["peak_viewers"], 80)
        self.assertEqual(row["total_duration"], "0 h 10 min")
