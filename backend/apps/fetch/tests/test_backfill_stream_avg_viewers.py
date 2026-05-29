"""Tests for the backfill_stream_avg_viewers one-shot command.

Recomputes Stream.avg_viewers for already-finalized streams (OFFLINE and
APPROVED) from the retained `snapshots` JSONB: the rounded mean of the
per-snapshot viewer counts. LIVE streams and streams with empty snapshots
must be left at 0. The command sweeps id ranges, is idempotent, and supports
--start-id/--stop-id resume bounds.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.streams.models import Stream, StreamerProfile


class BackfillStreamAvgViewersTests(TestCase):
    def setUp(self):
        self.profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )

    def _make_stream(self, host_stream_id, status, snapshots, avg_viewers=0):
        return Stream.objects.create(
            streamer_profile=self.profile,
            host_stream_id=host_stream_id,
            status=status,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=1),
            snapshots=snapshots,
            avg_viewers=avg_viewers,
        )

    @staticmethod
    def _snaps(*viewer_values):
        return [{"g": 100, "v": v, "t": 1700000000 + i} for i, v in enumerate(viewer_values)]

    def _run(self, *args):
        call_command("backfill_stream_avg_viewers", *args, stdout=mock.Mock())

    def test_offline_and_approved_streams_get_rounded_mean(self):
        offline = self._make_stream(1, Stream.Status.OFFLINE, self._snaps(80, 120, 50))
        approved = self._make_stream(2, Stream.Status.APPROVED, self._snaps(80, 90))

        self._run()

        offline.refresh_from_db()
        approved.refresh_from_db()
        # mean(80, 120, 50) = 83.33 -> 83
        self.assertEqual(offline.avg_viewers, 83)
        # mean(80, 90) = 85
        self.assertEqual(approved.avg_viewers, 85)

    def test_live_streams_are_untouched(self):
        """Live streams haven't finalized; their snapshots are still
        accumulating, so the backfill must leave avg_viewers at 0."""
        live = self._make_stream(1, Stream.Status.LIVE, self._snaps(80, 120))

        self._run()

        live.refresh_from_db()
        self.assertEqual(live.avg_viewers, 0)

    def test_empty_snapshots_stay_zero(self):
        empty = self._make_stream(1, Stream.Status.OFFLINE, [])

        self._run()

        empty.refresh_from_db()
        self.assertEqual(empty.avg_viewers, 0)

    def test_dry_run_does_not_write(self):
        offline = self._make_stream(1, Stream.Status.OFFLINE, self._snaps(80, 120, 50))

        self._run("--dry-run")

        offline.refresh_from_db()
        self.assertEqual(offline.avg_viewers, 0)

    def test_idempotent_across_repeated_runs(self):
        offline = self._make_stream(1, Stream.Status.OFFLINE, self._snaps(80, 120, 50))

        self._run()
        self._run()

        offline.refresh_from_db()
        self.assertEqual(offline.avg_viewers, 83)

    def test_recomputes_stale_value(self):
        """A row carrying a wrong/old avg_viewers is corrected from snapshots."""
        offline = self._make_stream(
            1, Stream.Status.OFFLINE, self._snaps(80, 90), avg_viewers=999
        )

        self._run()

        offline.refresh_from_db()
        self.assertEqual(offline.avg_viewers, 85)

    def test_start_and_stop_id_bound_the_sweep(self):
        """Streams outside [start-id, stop-id] are not processed."""
        before = self._make_stream(1, Stream.Status.OFFLINE, self._snaps(80, 90))
        inside = self._make_stream(2, Stream.Status.OFFLINE, self._snaps(40, 60))
        after = self._make_stream(3, Stream.Status.OFFLINE, self._snaps(10, 30))

        self._run("--start-id", str(inside.id), "--stop-id", str(inside.id))

        before.refresh_from_db()
        inside.refresh_from_db()
        after.refresh_from_db()
        self.assertEqual(before.avg_viewers, 0)
        self.assertEqual(inside.avg_viewers, 50)
        self.assertEqual(after.avg_viewers, 0)

    def test_small_batch_size_processes_all_rows(self):
        """A batch size smaller than the id span still drains every stream."""
        streams = [
            self._make_stream(i, Stream.Status.OFFLINE, self._snaps(100, 100))
            for i in range(1, 6)
        ]

        self._run("--batch-size", "1")

        for stream in streams:
            stream.refresh_from_db()
            self.assertEqual(stream.avg_viewers, 100)

    def test_no_finalized_streams_is_a_no_op(self):
        self._make_stream(1, Stream.Status.LIVE, self._snaps(80, 90))

        # Should not raise even though there is no finalized id range.
        self._run()

        self.assertEqual(Stream.objects.get().avg_viewers, 0)
