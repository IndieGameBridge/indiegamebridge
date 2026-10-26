"""Tests for delete_archived_streams: archived months leave Postgres only once their files check out."""

import contextlib
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.streams.archive import retention_start
from apps.streams.management.commands import delete_archived_streams
from apps.streams.models import ArchivedMonth, Stream, StreamerProfile


class DeleteArchivedStreamsTests(TestCase):
    def setUp(self):
        archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(archive_dir.cleanup)
        settings_override = override_settings(ARCHIVE_DIR=archive_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.files_dir = Path(archive_dir.name) / "streams"

        no_pause = mock.patch.object(delete_archived_streams, "PAUSE_SECONDS", 0)
        no_pause.start()
        self.addCleanup(no_pause.stop)

        self.cutoff = retention_start(timezone.now())
        # Moments in the last month before the retention window, and in the one before it.
        self.last_month = self.cutoff - timedelta(days=1)
        self.month_before = self.cutoff - timedelta(days=40)

        self.profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )
        self.next_host_stream_id = 1000

    def _stream(self, finished_at, status=Stream.Status.APPROVED, **fields):
        self.next_host_stream_id += 1
        return Stream.objects.create(
            streamer_profile=self.profile,
            host_stream_id=self.next_host_stream_id,
            status=status,
            language="en",
            started_at=finished_at - timedelta(hours=2),
            finished_at=finished_at,
            snapshots=[{"g": 33, "v": 7, "t": 1700000000}],
            **fields,
        )

    def _archive(self):
        call_command("archive_streams", stdout=StringIO())

    def _delete(self, *args):
        out = StringIO()
        call_command("delete_archived_streams", *args, stdout=out)
        return out.getvalue()

    def _month_file(self, moment):
        return self.files_dir / f"{moment:%Y-%m}.parquet"

    def test_deletes_an_archived_months_streams_and_marks_the_month(self):
        for _ in range(3):
            self._stream(self.last_month)
        live = self._stream(self.last_month, status=Stream.Status.LIVE)
        recent = self._stream(self.cutoff + timedelta(hours=1))
        self._archive()

        output = self._delete()

        self.assertCountEqual(Stream.objects.values_list("id", flat=True), [live.id, recent.id])
        self.assertIsNotNone(ArchivedMonth.objects.get().rows_deleted_at)
        self.assertIn(f"Deleted {self.last_month:%Y-%m}: 3 streams", output)
        # The file is the archive now; it stays.
        self.assertTrue(self._month_file(self.last_month).exists())

    def test_a_changed_file_leaves_the_streams_in_place(self):
        self._stream(self.last_month)
        self._archive()
        with open(self._month_file(self.last_month), "ab") as file:
            file.write(b"!")

        with self.assertRaises(CommandError):
            self._delete()

        self.assertEqual(Stream.objects.count(), 1)
        self.assertIsNone(ArchivedMonth.objects.get().rows_deleted_at)

    def test_a_missing_file_leaves_the_streams_in_place(self):
        self._stream(self.last_month)
        self._archive()
        self._month_file(self.last_month).unlink()

        with self.assertRaises(CommandError):
            self._delete()

        self.assertEqual(Stream.objects.count(), 1)

    def test_a_stream_missing_from_the_file_is_never_deleted(self):
        first, gap, last = (self._stream(self.last_month) for _ in range(3))
        gap_id, gap_host_stream_id = gap.id, gap.host_stream_id
        gap.delete()
        self._archive()
        # A stream of the month, inside the file's id range, that the file doesn't hold.
        Stream.objects.create(
            id=gap_id,
            streamer_profile=self.profile,
            host_stream_id=gap_host_stream_id,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=self.last_month - timedelta(hours=2),
            finished_at=self.last_month,
        )

        with self.assertRaises(CommandError):
            self._delete()

        self.assertCountEqual(Stream.objects.values_list("id", flat=True), [first.id, gap_id, last.id])
        self.assertIsNone(ArchivedMonth.objects.get().rows_deleted_at)

    def test_max_streams_stops_early_and_the_next_run_carries_on(self):
        for _ in range(3):
            self._stream(self.last_month)
        self._archive()

        with mock.patch.object(delete_archived_streams, "BATCH_IDS", 1):
            output = self._delete("--max-streams", "2")
            self.assertIn("stopped at --max-streams", output)
            self.assertEqual(Stream.objects.count(), 1)
            self.assertIsNone(ArchivedMonth.objects.get().rows_deleted_at)

            self._delete()

        self.assertEqual(Stream.objects.count(), 0)
        self.assertIsNotNone(ArchivedMonth.objects.get().rows_deleted_at)

    def test_months_out_of_postgres_already_are_skipped(self):
        self._stream(self.last_month)
        self._archive()
        self._delete()

        self.assertIn("Nothing to delete", self._delete())

    def test_month_option_deletes_just_that_month(self):
        in_last_month = self._stream(self.last_month)
        self._stream(self.month_before)
        self._archive()

        self._delete("--month", f"{self.month_before:%Y-%m}")

        self.assertEqual(list(Stream.objects.values_list("id", flat=True)), [in_last_month.id])
        self.assertEqual(
            list(ArchivedMonth.objects.filter(rows_deleted_at__isnull=True).values_list("month", flat=True)),
            [self.last_month.date().replace(day=1)],
        )

    def test_does_not_start_while_another_run_holds_the_lock(self):
        self._stream(self.last_month)
        self._archive()

        with mock.patch.object(delete_archived_streams, "archive_lock", return_value=contextlib.nullcontext(False)):
            output = self._delete()

        self.assertIn("Another archive run is in progress", output)
        self.assertEqual(Stream.objects.count(), 1)
