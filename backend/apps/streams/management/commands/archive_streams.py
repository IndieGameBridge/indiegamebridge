"""Keep the stream archive up to date. Meant for cron once a day.

Each run does what's due, in this order:
  1. On Mondays, the opt-out cleanup (apps.streams.archive_cleanup): the month files lose
     the streams of streamers who opted out.
  2. Once a month is over, its streams are written to ARCHIVE_DIR/streams/<YYYY-MM>.parquet,
     and the month is recorded in ArchivedMonth. Its streams stay in Postgres for now.
  3. A month whose file is new, or was rewritten, or was counted for other page languages,
     has its game history counted from the file into GameMonthStats (apps.streams.game_history).
  4. The streams that finished more than KEEP_DAYS ago are deleted from Postgres, a day at a
     time, taking the ids from their month's file, so no stream leaves Postgres without being
     in a file. Once a month's last day is out, Postgres is checked for streams of the month
     the file doesn't hold.

Writing a month's file reads the whole streams table once; on the other days, a run reads
only the day of streams it deletes.

The files can be read without Postgres; DuckDB, for one, queries them in place:

    SELECT language, count(*) FROM 'archive/streams/*.parquet' GROUP BY 1;
"""

import os
import time
from datetime import date, timedelta

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.jobs.recording import RecordedCommand
from apps.streams.archive import (
    KEEP_DAYS,
    archive_lock,
    deletion_cutoff,
    file_problem,
    files_dir,
    month_range,
    month_start,
    sha256_of,
)
from apps.streams.archive_cleanup import remove_opted_out
from apps.streams.game_history import count_month, needs_counting
from apps.streams.models import ArchivedMonth, Stream, StreamerProfile

# Streams read from Postgres, and written to Parquet as one row group, at a time.
BATCH_SIZE = 20000

# Streams deleted from Postgres by one statement, and the pause after each, so the deletes
# come in short bursts the fetch and the site work between.
DELETE_BATCH = 20000
PAUSE_SECONDS = 0.5

# What a run deletes at most, unless --max-streams says otherwise: a day's streams are far
# fewer, so this only spreads a backlog over several runs, about 6 minutes each.
MAX_DELETES = 2_000_000

STREAM_FIELDS = (
    "id",
    "host_stream_id",
    "streamer_profile_id",
    "status",
    "language",
    "started_at",
    "finished_at",
    "duration",
    "max_viewers",
    "avg_viewers",
    "host_game_ids",
    "genre_ids",
    "snapshots",
)

# The streamer as they are when the month is archived. host_user_id is Twitch's own
# id, which outlives a changed login and the profile row itself.
PROFILE_FIELDS = ("host_user_id", "host_login", "host_display_name")

# Stream's columns plus the streamer's. Snapshots keep the table's short keys:
# t = poll time (unix seconds), g = host_game_id, v = viewers.
SCHEMA = pa.schema([
    ("id", pa.int64()),
    ("host_stream_id", pa.int64()),
    ("streamer_profile_id", pa.int64()),
    ("host_user_id", pa.int64()),
    ("host_login", pa.string()),
    ("host_display_name", pa.string()),
    ("status", pa.string()),
    ("language", pa.string()),
    ("started_at", pa.timestamp("us", tz="UTC")),
    ("finished_at", pa.timestamp("us", tz="UTC")),
    ("duration", pa.int64()),
    ("max_viewers", pa.int64()),
    ("avg_viewers", pa.int64()),
    ("host_game_ids", pa.list_(pa.int64())),
    ("genre_ids", pa.list_(pa.int64())),
    ("snapshots", pa.list_(pa.struct([("t", pa.int64()), ("g", pa.int64()), ("v", pa.int64())]))),
])


class _MonthFile:
    """The Parquet file one month's streams are being written to. It's written under
    a .partial name, and takes its real one only once it checks out."""

    def __init__(self, month, directory):
        self.month = month
        self.path = directory / f"{month:%Y-%m}.parquet"
        self.partial_path = self.path.with_name(f"{self.path.name}.partial")
        self.writer = pq.ParquetWriter(self.partial_path, SCHEMA, compression="zstd")
        self.streams_count = 0
        self.first_stream_id = None
        self.last_stream_id = None

    def write(self, streams):
        self.writer.write_table(pa.Table.from_pylist(streams, schema=SCHEMA))
        self.streams_count += len(streams)
        ids = [one_stream["id"] for one_stream in streams]
        low, high = min(ids), max(ids)
        self.first_stream_id = low if self.first_stream_id is None else min(self.first_stream_id, low)
        self.last_stream_id = high if self.last_stream_id is None else max(self.last_stream_id, high)

    def close(self):
        if self.writer is not None:
            self.writer.close()
            self.writer = None

    def discard(self):
        self.close()
        self.partial_path.unlink(missing_ok=True)


class Command(RecordedCommand):
    help = (
        "Keep the stream archive up to date, once a day: on Mondays, remove opted-out streamers from the"
        " month files; once a month is over, write its streams to a Parquet file and count its game history;"
        f" and delete from Postgres the streams that finished more than {KEEP_DAYS} days ago, by the ids in"
        " their month's file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-streams",
            type=int,
            default=MAX_DELETES,
            help=f"Stop deleting once about this many streams are deleted; the next run carries on."
                f" Default {MAX_DELETES:,}; 0 deletes none.",
        )
        parser.add_argument(
            "--recount-history",
            action="store_true",
            help="Count every archived month's game history again, as after a change to how it's counted.",
        )

    def handle(self, *args, **options):
        with archive_lock() as locked:
            if not locked:
                self.stdout.write("Another archive run is in progress; not starting.")
                return
            started = time.monotonic()
            now = timezone.now()
            if now.weekday() == 0:
                rewritten, removed = remove_opted_out(self.stdout.write)
                self.count(rewritten=rewritten, removed=removed)
            self._archive(now)
            self._count_history(options["recount_history"])
            self._delete(now, options["max_streams"])
            self.stdout.write(f"Done in {timedelta(seconds=round(time.monotonic() - started))}.")

    # -- 2. The month files ---------------------------------------------------------------

    def _archive(self, now):
        """Write a file for every month that is over and has none yet: normally just last
        month, on the first run after it ended."""
        cutoff = month_start(now)
        last_month = (cutoff - timedelta(days=1)).date().replace(day=1)
        if ArchivedMonth.objects.filter(month=last_month).exists():
            return
        # The fetch closes a stream an hour after it was last seen; until it has, the stream
        # could still end in last month, after its file was written.
        still_open = Stream.objects.filter(status=Stream.Status.LIVE, finished_at__lt=cutoff).count()
        if still_open:
            self.stdout.write(
                f"Not writing {last_month:%Y-%m}'s file yet: {still_open:,} of its streams are still open;"
                " the next run tries again."
            )
            return

        streams = Stream.objects.filter(finished_at__lt=cutoff).exclude(status=Stream.Status.LIVE)
        for archived_month in ArchivedMonth.objects.values_list("month", flat=True):
            start, end = month_range(archived_month)
            streams = streams.exclude(finished_at__gte=start, finished_at__lt=end)

        started = time.monotonic()
        directory = files_dir()
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        try:
            self._export(streams, files, directory)
            for month in sorted(files):
                self._finish(files[month])
        except BaseException:
            # A month already finished keeps its file and record; the rest leave nothing behind.
            for one_file in files.values():
                one_file.discard()
            raise

        if not files:
            self.stdout.write(f"Nothing to archive: no unarchived streams finished before {cutoff:%Y-%m-%d}.")
            return
        self.stdout.write(f"Wrote the month files in {timedelta(seconds=round(time.monotonic() - started))}.")

    def _export(self, streams, files, directory):
        """Read the streams out of Postgres a batch at a time, each into its month's file."""
        # Inside a transaction the cursor streams its rows. Outside one, Django declares
        # it WITH HOLD, and Postgres copies the whole result to a temporary file first.
        with transaction.atomic():
            batch = []
            for one_stream in streams.values(*STREAM_FIELDS).iterator(chunk_size=BATCH_SIZE):
                batch.append(one_stream)
                if len(batch) == BATCH_SIZE:
                    self._write_batch(batch, files, directory)
                    batch = []
            if batch:
                self._write_batch(batch, files, directory)

    @staticmethod
    def _write_batch(batch, files, directory):
        """Write a batch of streams to their months' files, each with its streamer."""
        profiles = {
            profile_id: dict(zip(PROFILE_FIELDS, profile))
            for profile_id, *profile in StreamerProfile.objects.filter(
                id__in={one_stream["streamer_profile_id"] for one_stream in batch},
            ).values_list("id", *PROFILE_FIELDS)
        }
        by_month = {}
        for one_stream in batch:
            profile = profiles.get(one_stream["streamer_profile_id"])
            # Gone since the batch was read: the streamer opted out, which deletes their
            # streams too, so they stay out of the archive as well.
            if profile is None:
                continue
            one_stream.update(profile)
            finished_at = one_stream["finished_at"]
            by_month.setdefault(date(finished_at.year, finished_at.month, 1), []).append(one_stream)

        for month, streams in by_month.items():
            if month not in files:
                files[month] = _MonthFile(month, directory)
            files[month].write(streams)

    def _finish(self, month_file):
        """Check a month's file against what was written to it, give it its real name,
        and record the month."""
        month_file.close()
        with pq.ParquetFile(month_file.partial_path) as written:
            rows_in_file = written.metadata.num_rows
        if rows_in_file != month_file.streams_count:
            raise CommandError(
                f"{month_file.month:%Y-%m}: the file holds {rows_in_file:,} rows,"
                f" but {month_file.streams_count:,} streams were written to it."
            )

        sha256 = sha256_of(month_file.partial_path)
        os.replace(month_file.partial_path, month_file.path)
        archived_month = ArchivedMonth.objects.create(
            month=month_file.month,
            file_name=month_file.path.name,
            streams_count=month_file.streams_count,
            first_stream_id=month_file.first_stream_id,
            last_stream_id=month_file.last_stream_id,
            file_size=month_file.path.stat().st_size,
            sha256=sha256,
        )
        self.count(months=1, streams=archived_month.streams_count)
        self.stdout.write(
            f"Archived {archived_month.month:%Y-%m}: {archived_month.streams_count:,} streams"
            f" (ids {archived_month.first_stream_id}-{archived_month.last_stream_id}),"
            f" {archived_month.file_size / 1024 ** 2:,.1f} MB -> {month_file.path}"
        )

    # -- 3. The game history --------------------------------------------------------------

    def _count_history(self, recount):
        """Count the game history of each month whose file has changed since, or that was
        never counted; or of every month, with --recount-history."""
        for archived_month in ArchivedMonth.objects.order_by("month"):
            if not (recount or needs_counting(archived_month)):
                continue
            started = time.monotonic()
            rows = count_month(archived_month)
            self.count(history_months=1)
            self.stdout.write(
                f"Counted {archived_month.month:%Y-%m}'s game history: {rows:,} rows,"
                f" in {timedelta(seconds=round(time.monotonic() - started))}."
            )

    # -- 4. The deletes -------------------------------------------------------------------

    def _delete(self, now, max_streams):
        """Delete the archived streams that finished before the cutoff, oldest month first,
        stopping once about max_streams are gone."""
        if max_streams is not None and max_streams <= 0:
            self.stdout.write("Deleted nothing: --max-streams 0.")
            return
        cutoff = deletion_cutoff(now)
        deleted = 0
        months = ArchivedMonth.objects.filter(rows_deleted_at__isnull=True, month__lt=cutoff.date()).order_by("month")
        for archived_month in months:
            budget = None if max_streams is None else max_streams - deleted
            deleted_now, finished = self._delete_month(archived_month, cutoff, budget, now)
            deleted += deleted_now
            if not finished:
                self.stdout.write("Stopped at --max-streams; the next run carries on.")
                return
        if not deleted:
            self.stdout.write(f"Nothing to delete: no archived stream that finished before {cutoff:%Y-%m-%d} is left.")

    def _delete_month(self, archived_month, cutoff, budget, now):
        """Delete one month's streams that finished before the cutoff, a day at a time,
        stopping after the day that brings the deletes to budget.

        Returns how many were deleted, and whether every day due was done.
        """
        label = f"{archived_month.month:%Y-%m}"
        start, end = month_range(archived_month.month)
        upto = min(cutoff, end)
        through = archived_month.deleted_through or start
        deleted = 0
        if through < upto:
            path = files_dir() / archived_month.file_name
            problem = file_problem(archived_month, path)
            if problem:
                raise CommandError(f"{label}: {problem}; its streams were left in place.")
            table = pq.read_table(path, columns=["id", "finished_at"])
            ids, finished = table.column("id"), table.column("finished_at")
            while through < upto:
                day_end = min(through + timedelta(days=1), upto)
                in_day = pc.and_(
                    pc.greater_equal(finished, pa.scalar(through, finished.type)),
                    pc.less(finished, pa.scalar(day_end, finished.type)),
                )
                day_ids = sorted(ids.filter(in_day).to_pylist())
                for low in range(0, len(day_ids), DELETE_BATCH):
                    count, _ = Stream.objects.filter(id__in=day_ids[low:low + DELETE_BATCH]).delete()
                    deleted += count
                    self.count(deleted=count)
                    time.sleep(PAUSE_SECONDS)
                through = day_end
                archived_month.deleted_through = through
                archived_month.save(update_fields=["deleted_through"])
                if budget is not None and deleted >= budget and through < upto:
                    self.stdout.write(f"{label}: deleted {deleted:,} streams that finished before {through:%Y-%m-%d}.")
                    return deleted, False
            self.stdout.write(f"{label}: deleted {deleted:,} streams that finished before {through:%Y-%m-%d}.")

        if upto == end:
            self._check_nothing_left(archived_month, label, start, end)
            archived_month.rows_deleted_at = now
            archived_month.save(update_fields=["rows_deleted_at"])
            self.stdout.write(f"{label} is out of Postgres.")
        return deleted, True

    @staticmethod
    def _check_nothing_left(archived_month, label, start, end):
        """Refuse to call a month out of Postgres while it still has streams there, which
        can only be streams its file doesn't hold."""
        left = list(
            Stream.objects.filter(
                id__gte=archived_month.first_stream_id,
                id__lte=archived_month.last_stream_id,
                finished_at__gte=start,
                finished_at__lt=end,
            ).exclude(status=Stream.Status.LIVE).values_list("id", flat=True)[:1000]
        )
        if left:
            raise CommandError(
                f"{label}: {len(left):,}{'+' if len(left) == 1000 else ''} of its streams in Postgres aren't in its"
                f" file (id {left[0]}, for one); they were left in place."
            )
