"""Tests for the opt-out cleanup, run by hand through remove_opted_out_from_archive:
archived files lose the streams of streamers who opt out."""

import contextlib
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest import mock

import pyarrow.parquet as pq
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.streams.archive import sha256_of
from apps.streams.management.commands import archive_streams, remove_opted_out_from_archive
from apps.streams.models import ArchivedMonth, Stream, StreamerProfile
from apps.users.views.opt_out import perform_opt_out_for_twitch_id

UTC = dt_timezone.utc

# The first run after November, which writes its file; and one that deletes all of it.
DECEMBER_1 = datetime(2026, 12, 1, 10, 27, tzinfo=UTC)
JANUARY_10 = datetime(2027, 1, 10, 10, 27, tzinfo=UTC)


class RemoveOptedOutFromArchiveTests(TestCase):
    def setUp(self):
        archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(archive_dir.cleanup)
        settings_override = override_settings(ARCHIVE_DIR=archive_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.files_dir = Path(archive_dir.name) / "streams"

        no_pause = mock.patch.object(archive_streams, "PAUSE_SECONDS", 0)
        no_pause.start()
        self.addCleanup(no_pause.stop)

        self.staying = self._profile(2001, "staying")
        self.leaving = self._profile(2002, "leaving")
        self.next_host_stream_id = 1000

    @staticmethod
    def _profile(host_user_id, login):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _stream(self, profile, day=15):
        self.next_host_stream_id += 1
        finished_at = datetime(2026, 11, day, 12, tzinfo=UTC)
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=self.next_host_stream_id,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=finished_at - timedelta(hours=2),
            finished_at=finished_at,
            snapshots=[{"g": 33, "v": 7, "t": 1700000000}],
        )

    @staticmethod
    def _archive(now, *args):
        with mock.patch("django.utils.timezone.now", return_value=now):
            call_command("archive_streams", *args, stdout=StringIO())

    def _remove(self, *args):
        out = StringIO()
        call_command("remove_opted_out_from_archive", *args, stdout=out)
        return out.getvalue()

    def _month_file(self):
        return self.files_dir / "2026-11.parquet"

    def _ids_in_file(self):
        return pq.read_table(self._month_file(), columns=["id"]).column("id").to_pylist()

    def test_rewrites_the_file_without_the_opted_out_streams_and_updates_the_record(self):
        # The month's first and last streams are the leaving streamer's, so its ids narrow.
        self._stream(self.leaving)
        staying = [self._stream(self.staying) for _ in range(2)]
        self._stream(self.leaving)
        self._archive(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)

        output = self._remove()

        self.assertCountEqual(self._ids_in_file(), [one_stream.id for one_stream in staying])
        archived_month = ArchivedMonth.objects.get()
        self.assertEqual(archived_month.streams_count, 2)
        self.assertEqual(archived_month.first_stream_id, staying[0].id)
        self.assertEqual(archived_month.last_stream_id, staying[1].id)
        self.assertEqual(archived_month.file_size, self._month_file().stat().st_size)
        self.assertEqual(archived_month.sha256, sha256_of(self._month_file()))
        self.assertIsNotNone(archived_month.rewritten_at)
        self.assertIn("Rewrote 2026-11: removed 2 streams of 1 opted-out streamers", output)
        self.assertFalse(list(self.files_dir.glob("*.partial")))

        # The rewritten file still checks out, so the month can leave Postgres.
        self._archive(JANUARY_10)
        self.assertEqual(Stream.objects.count(), 0)
        self.assertIsNotNone(ArchivedMonth.objects.get().rows_deleted_at)

    def test_works_on_a_month_partly_out_of_postgres(self):
        for day in (3, 5):
            self._stream(self.staying, day)
            self._stream(self.leaving, day)
        self._archive(DECEMBER_1)
        # Deletes the 3rd, then stops.
        self._archive(JANUARY_10, "--max-streams", "1")
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)

        self._remove()
        self._archive(JANUARY_10)

        self.assertEqual(Stream.objects.count(), 0)
        self.assertEqual(len(self._ids_in_file()), 2)
        self.assertIsNotNone(ArchivedMonth.objects.get().rows_deleted_at)

    def test_a_file_with_nothing_to_remove_is_left_as_it_is(self):
        self._stream(self.staying)
        self._archive(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)
        sha256 = sha256_of(self._month_file())

        output = self._remove()

        self.assertIn("Nothing to remove", output)
        self.assertEqual(sha256_of(self._month_file()), sha256)
        self.assertIsNone(ArchivedMonth.objects.get().rewritten_at)

    def test_dry_run_only_counts(self):
        self._stream(self.staying)
        self._stream(self.leaving)
        self._archive(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)
        sha256 = sha256_of(self._month_file())

        output = self._remove("--dry-run")

        self.assertIn("2026-11: would remove 1 streams of 1 opted-out streamers", output)
        self.assertEqual(sha256_of(self._month_file()), sha256)
        self.assertEqual(ArchivedMonth.objects.get().streams_count, 2)

    def test_a_changed_file_is_left_as_it_is(self):
        self._stream(self.staying)
        self._stream(self.leaving)
        self._archive(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)
        archived_month = ArchivedMonth.objects.get()
        archived_month.sha256 = "0" * 64
        archived_month.save(update_fields=["sha256"])

        with self.assertRaises(CommandError):
            self._remove()

        self.assertEqual(len(self._ids_in_file()), 2)
        self.assertIsNone(ArchivedMonth.objects.get().rewritten_at)

    def test_does_not_start_while_another_run_holds_the_lock(self):
        self._stream(self.leaving)
        self._archive(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.leaving.host_user_id)

        with mock.patch.object(
            remove_opted_out_from_archive, "archive_lock", return_value=contextlib.nullcontext(False),
        ):
            output = self._remove()

        self.assertIn("Another archive run is in progress", output)
        self.assertEqual(len(self._ids_in_file()), 1)
