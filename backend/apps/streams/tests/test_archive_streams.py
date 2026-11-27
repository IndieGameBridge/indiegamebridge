"""Tests for archive_streams, the daily run: the month files, their game history, the
deletes from Postgres, and the Monday opt-out cleanup."""

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

from apps.streams import archive, game_history
from apps.streams.archive import archive_lock, deletion_cutoff, month_start
from apps.streams.management.commands import archive_streams
from apps.streams.models import ArchivedMonth, Game, GameMonthStats, Stream, StreamerProfile
from apps.users.views.opt_out import perform_opt_out_for_twitch_id

UTC = dt_timezone.utc

# Run days: the 1st of a month (a Tuesday), the Monday after, and a day in January.
DECEMBER_1 = datetime(2026, 12, 1, 10, 27, tzinfo=UTC)
MONDAY = datetime(2026, 12, 7, 10, 27, tzinfo=UTC)
JANUARY_10 = datetime(2027, 1, 10, 10, 27, tzinfo=UTC)


def at(day, hour=12, month=11, year=2026):
    return datetime(year, month, day, hour, tzinfo=UTC)


class WindowTests(SimpleTestCase):
    def test_streams_leave_postgres_at_the_start_of_the_day_5_weeks_back(self):
        self.assertEqual(deletion_cutoff(DECEMBER_1), datetime(2026, 10, 27, tzinfo=UTC))
        self.assertEqual(deletion_cutoff(datetime(2026, 12, 1, 23, 59, tzinfo=UTC)), datetime(2026, 10, 27, tzinfo=UTC))

    def test_postgres_always_keeps_the_4_weeks_the_pages_read_and_a_week_more(self):
        for hour in (0, 10, 23):
            now = datetime(2027, 3, 1, hour, tzinfo=UTC)
            self.assertGreaterEqual(now - deletion_cutoff(now), timedelta(weeks=4) + timedelta(weeks=1))

    def test_a_month_can_be_written_once_the_next_one_has_begun(self):
        self.assertEqual(month_start(DECEMBER_1), datetime(2026, 12, 1, tzinfo=UTC))
        self.assertEqual(month_start(datetime(2027, 1, 1, 0, 5, tzinfo=UTC)), datetime(2027, 1, 1, tzinfo=UTC))


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


class ArchiveTestCase(TestCase):
    """A temporary archive folder, a streamer, games, and runs at a chosen moment."""

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

        self.profile = self._profile(2001, "loginx")
        self.next_host_stream_id = 1000
        self.game = Game.objects.create(host_game_id=33, host_name="Game 33", category=Game.Category.ISGAME)

    @staticmethod
    def _profile(host_user_id, login):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _stream(self, finished_at, status=Stream.Status.APPROVED, profile=None, **fields):
        self.next_host_stream_id += 1
        return Stream.objects.create(
            streamer_profile=profile or self.profile,
            host_stream_id=self.next_host_stream_id,
            status=status,
            language=fields.pop("language", "en"),
            started_at=finished_at - timedelta(hours=2),
            finished_at=finished_at,
            duration=fields.pop("duration", 7200),
            host_game_ids=fields.pop("host_game_ids", [33]),
            snapshots=fields.pop("snapshots", [{"g": 33, "v": 7, "t": 1700000000}]),
            **fields,
        )

    def _run(self, now, *args):
        out = StringIO()
        with mock.patch("django.utils.timezone.now", return_value=now):
            call_command("archive_streams", *args, stdout=out)
        return out.getvalue()

    def _file(self, month="2026-11"):
        return self.files_dir / f"{month}.parquet"

    def _rows(self, month="2026-11"):
        return pq.read_table(self._file(month)).to_pylist()


class MonthFileTests(ArchiveTestCase):
    def test_writes_last_months_file_once_it_is_over_and_keeps_its_streams(self):
        november = self._stream(at(15))
        self._stream(datetime(2026, 12, 1, 9, tzinfo=UTC))

        output = self._run(DECEMBER_1)

        self.assertEqual([row["id"] for row in self._rows()], [november.id])
        archived_month = ArchivedMonth.objects.get()
        self.assertEqual(
            (archived_month.month, archived_month.streams_count, archived_month.first_stream_id),
            (at(1).date(), 1, november.id),
        )
        self.assertIn("Archived 2026-11", output)
        # The file is written, but both streams are younger than 5 weeks: they stay.
        self.assertEqual(Stream.objects.count(), 2)

    def test_writes_every_month_that_has_no_file_in_one_go(self):
        for month in (9, 10, 11):
            self._stream(at(10, month=month))

        self._run(DECEMBER_1)

        self.assertEqual(
            [f"{one:%Y-%m}" for one in ArchivedMonth.objects.values_list("month", flat=True)],
            ["2026-09", "2026-10", "2026-11"],
        )

    def test_waits_while_a_stream_of_last_month_is_still_open(self):
        self._stream(at(30, hour=23), status=Stream.Status.LIVE)
        self._stream(at(15))

        output = self._run(DECEMBER_1)

        self.assertIn("Not writing 2026-11's file yet: 1 of its streams are still open", output)
        self.assertFalse(ArchivedMonth.objects.exists())

    def test_a_month_with_a_file_is_not_written_again(self):
        self._stream(at(15))
        self._run(DECEMBER_1)
        first = ArchivedMonth.objects.get()

        with mock.patch.object(archive_streams.Command, "_export") as export:
            self._run(DECEMBER_1 + timedelta(days=1))

        export.assert_not_called()
        self.assertEqual(ArchivedMonth.objects.get().sha256, first.sha256)

    def test_a_file_holds_the_stream_with_its_streamer(self):
        stream = self._stream(
            at(15),
            duration=7200,
            max_viewers=12,
            avg_viewers=8,
            host_game_ids=[33, 44],
            genre_ids=[5],
            snapshots=[{"g": 33, "v": 7, "t": 1700000000}, {"g": 44, "v": 12, "t": 1700001200}],
        )

        self._run(DECEMBER_1)

        self.assertEqual(self._rows(), [{
            "id": stream.id,
            "host_stream_id": stream.host_stream_id,
            "streamer_profile_id": self.profile.id,
            "host_user_id": 2001,
            "host_login": "loginx",
            "host_display_name": "Loginx",
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
        self._stream(at(15))

        self._run(DECEMBER_1)

        archived_month = ArchivedMonth.objects.get()
        path = self.files_dir / archived_month.file_name
        self.assertEqual(archived_month.file_size, path.stat().st_size)
        self.assertEqual(archived_month.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(list(self.files_dir.glob("*.partial")), [])

    def test_offline_streams_are_archived_too(self):
        self._stream(at(15), status=Stream.Status.OFFLINE)

        self._run(DECEMBER_1)

        self.assertEqual([row["status"] for row in self._rows()], ["offline"])

    def test_does_not_start_while_another_run_holds_the_lock(self):
        self._stream(at(15))

        with mock.patch.object(archive_streams, "archive_lock", return_value=contextlib.nullcontext(False)):
            output = self._run(DECEMBER_1)

        self.assertIn("Another archive run is in progress", output)
        self.assertFalse(ArchivedMonth.objects.exists())

    def test_a_file_that_does_not_check_out_is_dropped(self):
        self._stream(at(15))

        with mock.patch.object(archive_streams.pq, "ParquetFile") as parquet_file:
            parquet_file.return_value.__enter__.return_value.metadata.num_rows = 99
            with self.assertRaises(CommandError):
                self._run(DECEMBER_1)

        self.assertFalse(ArchivedMonth.objects.exists())
        self.assertEqual(list(self.files_dir.iterdir()), [])


class DeleteTests(ArchiveTestCase):
    def test_deletes_the_streams_older_than_5_weeks_by_their_files(self):
        early, late = self._stream(at(10)), self._stream(at(30))
        december_3, december_20 = self._stream(at(3, month=12)), self._stream(at(20, month=12))
        january = self._stream(at(9, month=1, year=2027))
        self._run(DECEMBER_1)

        output = self._run(JANUARY_10)

        # The cutoff is 6 December: November is out, and December up to its 6th.
        self.assertCountEqual(Stream.objects.values_list("id", flat=True), [december_20.id, january.id])
        november, december = ArchivedMonth.objects.order_by("month")
        self.assertIsNotNone(november.rows_deleted_at)
        self.assertIsNone(december.rows_deleted_at)
        self.assertEqual(december.deleted_through, datetime(2026, 12, 6, tzinfo=UTC))
        self.assertIn("2026-11 is out of Postgres", output)
        # The files are the archive now; they stay.
        self.assertTrue(self._file().exists())
        self.assertNotIn(early.id, Stream.objects.values_list("id", flat=True))
        self.assertNotIn(late.id, Stream.objects.values_list("id", flat=True))
        self.assertNotIn(december_3.id, Stream.objects.values_list("id", flat=True))

    def test_each_run_deletes_the_days_that_left_the_window_since(self):
        self._stream(at(3, month=12))
        december_20 = self._stream(at(20, month=12))
        self._run(datetime(2027, 1, 2, 10, 27, tzinfo=UTC))

        self.assertIn("Nothing to delete", self._run(datetime(2027, 1, 3, 10, 27, tzinfo=UTC)))
        self.assertEqual(Stream.objects.count(), 2)

        self._run(datetime(2027, 1, 10, 10, 27, tzinfo=UTC))
        self.assertEqual(list(Stream.objects.values_list("id", flat=True)), [december_20.id])

        self._run(datetime(2027, 1, 25, 10, 27, tzinfo=UTC))
        self.assertFalse(Stream.objects.exists())
        self.assertEqual(
            ArchivedMonth.objects.get().deleted_through, datetime(2026, 12, 21, tzinfo=UTC),
        )

    def test_max_streams_stops_after_a_day_and_the_next_run_carries_on(self):
        for day in (3, 4, 5):
            self._stream(at(day))
            self._stream(at(day))
        self._run(DECEMBER_1)

        output = self._run(JANUARY_10, "--max-streams", "1")

        self.assertIn("Stopped at --max-streams", output)
        self.assertEqual(Stream.objects.count(), 4)
        self.assertEqual(ArchivedMonth.objects.get(month=at(1).date()).deleted_through, at(4, hour=0))

        self._run(JANUARY_10)

        self.assertEqual(Stream.objects.count(), 0)
        self.assertIsNotNone(ArchivedMonth.objects.get(month=at(1).date()).rows_deleted_at)

    def test_max_streams_0_deletes_none(self):
        self._stream(at(15))
        self._run(DECEMBER_1)

        output = self._run(JANUARY_10, "--max-streams", "0")

        self.assertIn("Deleted nothing", output)
        self.assertEqual(Stream.objects.count(), 1)
        self.assertIsNone(ArchivedMonth.objects.get(month=at(1).date()).deleted_through)

    def test_a_changed_file_leaves_the_streams_in_place(self):
        self._stream(at(15))
        self._run(DECEMBER_1)
        with open(self._file(), "ab") as file:
            file.write(b"!")

        with self.assertRaises(CommandError):
            self._run(JANUARY_10)

        self.assertEqual(Stream.objects.count(), 1)
        self.assertIsNone(ArchivedMonth.objects.get(month=at(1).date()).rows_deleted_at)

    def test_a_stream_its_file_lacks_is_never_deleted_and_holds_the_month_back(self):
        first, gap, last = (self._stream(at(15)) for _ in range(3))
        gap_id, gap_host_stream_id = gap.id, gap.host_stream_id
        gap.delete()
        self._run(DECEMBER_1)
        # A stream of the month, inside the file's id range, that the file doesn't hold.
        Stream.objects.create(
            id=gap_id,
            streamer_profile=self.profile,
            host_stream_id=gap_host_stream_id,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=at(15) - timedelta(hours=2),
            finished_at=at(15),
        )

        with self.assertRaises(CommandError):
            self._run(JANUARY_10)

        self.assertEqual(list(Stream.objects.values_list("id", flat=True)), [gap_id])
        self.assertIsNone(ArchivedMonth.objects.get(month=at(1).date()).rows_deleted_at)


class GameHistoryTests(ArchiveTestCase):
    def setUp(self):
        super().setUp()
        self.other_game = Game.objects.create(host_game_id=44, host_name="Game 44", category=Game.Category.ISGAME)
        Game.objects.create(host_game_id=509658, host_name="Just Chatting", category=Game.Category.ISNONGAME)
        self.streamer_b = self._profile(2002, "streamerb")
        self.streamer_c = self._profile(2003, "streamerc")

    def _stats(self, game=None):
        return {
            row.language: (row.streamers, row.streams, row.seconds, row.viewer_seconds, row.snapshot_seconds)
            for row in GameMonthStats.objects.filter(game=game or self.game, month=at(1).date())
        }

    def _november(self):
        # Two games in one stream: its 2 hours split evenly; 3 snapshots of 40 minutes each.
        self._stream(at(10), duration=7200, host_game_ids=[33, 44], snapshots=[
            {"g": 33, "v": 10, "t": 1}, {"g": 33, "v": 20, "t": 2}, {"g": 44, "v": 30, "t": 3},
        ])
        self._stream(at(11), duration=3600, snapshots=[{"g": 33, "v": 5, "t": 1}, {"g": 33, "v": 5, "t": 2}])
        # Just Chatting takes half the time, and isn't a game.
        self._stream(at(12), profile=self.streamer_b, language="fr", duration=1800, host_game_ids=[33, 509658],
                     snapshots=[{"g": 33, "v": 4, "t": 1}, {"g": 509658, "v": 100, "t": 2}])
        # The same streamer in English: once in the totals.
        self._stream(at(13), profile=self.streamer_b, duration=3600,
                     snapshots=[{"g": 33, "v": 1, "t": 1}, {"g": 33, "v": 3, "t": 2}])
        # A language collected but not on the pages yet: its own row, out of the totals.
        self._stream(at(14), profile=self.streamer_c, language="ru", duration=1200,
                     snapshots=[{"g": 33, "v": 2, "t": 1}, {"g": 33, "v": 2, "t": 2}])
        # Never approved: left out.
        self._stream(at(15), profile=self.streamer_c, status=Stream.Status.OFFLINE)

    def test_counts_a_new_files_game_history(self):
        self._november()

        output = self._run(DECEMBER_1)

        self.assertEqual(self._stats(), {
            # (streamers, streams, seconds played, viewer-seconds, snapshot-seconds)
            "en": (2, 3, 10800, 97200, 12000),
            "fr": (1, 1, 900, 3600, 900),
            "ru": (1, 1, 1200, 2400, 1200),
            "all": (2, 4, 11700, 100800, 12900),
        })
        self.assertEqual(self._stats(self.other_game), {
            "en": (1, 1, 3600, 72000, 2400),
            "all": (1, 1, 3600, 72000, 2400),
        })
        self.assertFalse(GameMonthStats.objects.exclude(game__in=[self.game, self.other_game]).exists())
        archived_month = ArchivedMonth.objects.get()
        self.assertIsNotNone(archived_month.stats_computed_at)
        self.assertIn("Counted 2026-11's game history: 6 rows", output)

    def test_a_month_already_counted_is_left_alone(self):
        self._november()
        self._run(DECEMBER_1)

        with mock.patch.object(archive_streams, "count_month") as count:
            self._run(DECEMBER_1 + timedelta(days=1))

        count.assert_not_called()

    def test_mondays_remove_opted_out_streamers_and_count_the_file_again(self):
        self._november()
        self._run(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.profile.host_user_id)

        output = self._run(MONDAY)

        self.assertIn("Rewrote 2026-11: removed 2 streams of 1 opted-out streamers", output)
        self.assertEqual(self._stats(), {
            "en": (1, 1, 3600, 7200, 3600),
            "fr": (1, 1, 900, 3600, 900),
            "ru": (1, 1, 1200, 2400, 1200),
            "all": (1, 2, 4500, 10800, 4500),
        })
        self.assertEqual(self._stats(self.other_game), {})

    def test_other_days_leave_the_files_to_monday(self):
        self._november()
        self._run(DECEMBER_1)
        perform_opt_out_for_twitch_id(self.profile.host_user_id)

        self._run(MONDAY + timedelta(days=1))

        self.assertEqual(len(self._rows()), 6)
        self.assertIsNone(ArchivedMonth.objects.get().rewritten_at)

    def test_a_month_is_counted_again_when_the_pages_offer_other_languages(self):
        self._november()
        self._run(DECEMBER_1)

        with mock.patch.object(game_history, "PAGE_LANGUAGES", game_history.PAGE_LANGUAGES + ("ru",)):
            self._run(DECEMBER_1 + timedelta(days=1))

        self.assertEqual(self._stats()["all"], (3, 5, 12900, 103200, 14100))
        self.assertIn("ru", ArchivedMonth.objects.get().stats_languages)

    def test_recount_history_counts_every_month_again(self):
        self._november()
        self._run(DECEMBER_1)
        counted_at = ArchivedMonth.objects.get().stats_computed_at

        self._run(DECEMBER_1 + timedelta(days=1), "--recount-history")

        self.assertGreater(ArchivedMonth.objects.get().stats_computed_at, counted_at)
        self.assertEqual(self._stats()["all"], (2, 4, 11700, 100800, 12900))

    def test_a_changed_file_is_not_counted(self):
        self._november()
        self._run(DECEMBER_1)
        with open(self._file(), "ab") as file:
            file.write(b"!")

        with self.assertRaises(CommandError):
            self._run(DECEMBER_1 + timedelta(days=1), "--recount-history")

        self.assertEqual(self._stats()["all"], (2, 4, 11700, 100800, 12900))
