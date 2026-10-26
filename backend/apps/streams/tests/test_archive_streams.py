"""Tests for archive_streams: which streams go to which month's file, and what the file holds."""

import contextlib
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest import mock

import pyarrow.parquet as pq
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.streams import archive
from apps.streams.archive import archive_lock, retention_start
from apps.streams.management.commands import archive_streams
from apps.streams.models import ArchivedMonth, Stream, StreamerProfile

UTC = dt_timezone.utc


class RetentionStartTests(SimpleTestCase):
    def test_keeps_the_current_month_and_two_full_months_before_it(self):
        self.assertEqual(
            retention_start(datetime(2026, 11, 1, 3, 0, tzinfo=UTC)),
            datetime(2026, 9, 1, tzinfo=UTC),
        )
        self.assertEqual(
            retention_start(datetime(2026, 10, 31, 23, 59, tzinfo=UTC)),
            datetime(2026, 8, 1, tzinfo=UTC),
        )

    def test_reaches_back_across_a_new_year(self):
        self.assertEqual(
            retention_start(datetime(2027, 2, 15, tzinfo=UTC)),
            datetime(2026, 12, 1, tzinfo=UTC),
        )

    def test_always_keeps_at_least_8_weeks(self):
        # Right after the run on the 1st is when Postgres holds the least.
        for year, month in [(2027, 3), (2027, 2), (2026, 8), (2028, 3)]:
            now = datetime(year, month, 1, tzinfo=UTC)
            self.assertGreaterEqual(now - retention_start(now), timedelta(weeks=8))


class ArchiveLockTests(TestCase):
    def _try_lock(self, connection):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [archive._LOCK_KEY])
            return cursor.fetchone()[0]

    def test_another_session_cannot_take_it_until_it_is_released(self):
        other = connections.create_connection(DEFAULT_DB_ALIAS)
        self.addCleanup(other.close)

        with archive_lock() as locked:
            self.assertTrue(locked)
            self.assertFalse(self._try_lock(other))

        self.assertTrue(self._try_lock(other))
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [archive._LOCK_KEY])

    def test_yields_false_while_another_session_holds_it(self):
        other = connections.create_connection(DEFAULT_DB_ALIAS)
        self.addCleanup(other.close)
        self.assertTrue(self._try_lock(other))

        with archive_lock() as locked:
            self.assertFalse(locked)


class ArchiveStreamsTests(TestCase):
    def setUp(self):
        archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(archive_dir.cleanup)
        settings_override = override_settings(ARCHIVE_DIR=archive_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.files_dir = Path(archive_dir.name) / "streams"

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
            snapshots=fields.pop("snapshots", [{"g": 33, "v": 7, "t": 1700000000}]),
            **fields,
        )

    def _run(self, *args):
        out = StringIO()
        call_command("archive_streams", *args, stdout=out)
        return out.getvalue()

    def _rows(self, moment):
        return pq.read_table(self.files_dir / f"{moment:%Y-%m}.parquet").to_pylist()

    def test_each_month_before_the_window_gets_its_own_file(self):
        last = self._stream(self.last_month)
        before = self._stream(self.month_before)
        self._stream(self.cutoff + timedelta(hours=1))

        output = self._run()

        self.assertEqual([row["id"] for row in self._rows(self.last_month)], [last.id])
        self.assertEqual([row["id"] for row in self._rows(self.month_before)], [before.id])
        self.assertEqual(
            [
                (one.month, one.streams_count, one.first_stream_id, one.last_stream_id)
                for one in ArchivedMonth.objects.all()
            ],
            [
                (self.month_before.date().replace(day=1), 1, before.id, before.id),
                (self.last_month.date().replace(day=1), 1, last.id, last.id),
            ],
        )
        self.assertIn(f"Archived {self.last_month:%Y-%m}", output)
        # Writing the files leaves the streams in Postgres.
        self.assertEqual(Stream.objects.count(), 3)

    def test_a_file_holds_the_stream_with_its_streamer(self):
        stream = self._stream(
            self.last_month,
            duration=7200,
            max_viewers=12,
            avg_viewers=8,
            host_game_ids=[33, 44],
            genre_ids=[5],
            snapshots=[{"g": 33, "v": 7, "t": 1700000000}, {"g": 44, "v": 12, "t": 1700001200}],
        )

        self._run()

        self.assertEqual(self._rows(self.last_month), [{
            "id": stream.id,
            "host_stream_id": stream.host_stream_id,
            "streamer_profile_id": self.profile.id,
            "host_user_id": 2001,
            "host_login": "loginx",
            "host_display_name": "DisplayName",
            "status": "approved",
            "language": "en",
            "started_at": stream.started_at,
            "finished_at": stream.finished_at,
            "duration": 7200,
            "max_viewers": 12,
            "avg_viewers": 8,
            "host_game_ids": [33, 44],
            "genre_ids": [5],
            "snapshots": [{"t": 1700000000, "g": 33, "v": 7}, {"t": 1700001200, "g": 44, "v": 12}],
        }])

    def test_the_record_describes_the_file(self):
        self._stream(self.last_month)

        self._run()

        archived_month = ArchivedMonth.objects.get()
        path = self.files_dir / archived_month.file_name
        self.assertEqual(archived_month.file_size, path.stat().st_size)
        self.assertEqual(archived_month.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(list(self.files_dir.glob("*.partial")), [])

    def test_offline_streams_are_archived_too(self):
        self._stream(self.last_month, status=Stream.Status.OFFLINE)

        self._run()

        self.assertEqual([row["status"] for row in self._rows(self.last_month)], ["offline"])

    def test_live_and_recent_streams_stay_out(self):
        self._stream(self.last_month, status=Stream.Status.LIVE)
        self._stream(self.cutoff)

        output = self._run()

        self.assertIn("Nothing to archive", output)
        self.assertFalse(ArchivedMonth.objects.exists())
        self.assertEqual(list(self.files_dir.iterdir()), [])

    def test_an_archived_month_is_not_written_again(self):
        self._stream(self.last_month)
        self._run()
        first = ArchivedMonth.objects.get()

        self._stream(self.month_before)
        output = self._run()

        self.assertNotIn(f"Archived {self.last_month:%Y-%m}", output)
        self.assertEqual(ArchivedMonth.objects.get(month=first.month).sha256, first.sha256)
        self.assertEqual(ArchivedMonth.objects.count(), 2)

    def test_month_option_archives_just_that_month(self):
        self._stream(self.last_month)
        self._stream(self.month_before)

        self._run("--month", f"{self.month_before:%Y-%m}")

        self.assertEqual(
            list(ArchivedMonth.objects.values_list("month", flat=True)),
            [self.month_before.date().replace(day=1)],
        )
        self.assertFalse((self.files_dir / f"{self.last_month:%Y-%m}.parquet").exists())

    def test_month_option_refuses_a_month_inside_the_window(self):
        with self.assertRaises(CommandError):
            self._run("--month", f"{self.cutoff:%Y-%m}")

    def test_month_option_says_when_the_month_is_archived_already(self):
        self._stream(self.last_month)
        self._run()

        self.assertIn("archived already", self._run("--month", f"{self.last_month:%Y-%m}"))

    def test_does_not_start_while_another_run_holds_the_lock(self):
        self._stream(self.last_month)

        with mock.patch.object(archive_streams, "archive_lock", return_value=contextlib.nullcontext(False)):
            output = self._run()

        self.assertIn("Another archive run is in progress", output)
        self.assertFalse(ArchivedMonth.objects.exists())

    def test_a_file_that_does_not_check_out_is_dropped(self):
        self._stream(self.last_month)

        with mock.patch.object(archive_streams.pq, "ParquetFile") as parquet_file:
            parquet_file.return_value.__enter__.return_value.metadata.num_rows = 99
            with self.assertRaises(CommandError):
                self._run()

        self.assertFalse(ArchivedMonth.objects.exists())
        self.assertEqual(list(self.files_dir.iterdir()), [])
