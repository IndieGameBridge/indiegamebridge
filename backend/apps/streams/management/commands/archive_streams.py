"""Write finished streams older than the retention window to monthly Parquet files.

Postgres keeps the current month and the KEEP_FULL_MONTHS full months before it.
Streams that finished earlier are written to ARCHIVE_DIR/streams/<YYYY-MM>.parquet,
one file per month, and each month is recorded in ArchivedMonth. The streams
themselves stay in Postgres.

The files can be read without Postgres; DuckDB, for one, queries them in place:

    SELECT language, count(*) FROM 'archive/streams/*.parquet' GROUP BY 1;
"""

import hashlib
import os
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.streams.models import ArchivedMonth, Stream, StreamerProfile

# Postgres keeps the current month and this many full months before it. Two months
# are never less than 59 days, so Postgres always holds at least 8 weeks.
KEEP_FULL_MONTHS = 2

# Streams read from Postgres, and written to Parquet as one row group, at a time.
BATCH_SIZE = 20000

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


def retention_start(now):
    """When the streams Postgres keeps start: the first moment (UTC) of the month
    KEEP_FULL_MONTHS before the current one."""
    months = now.year * 12 + now.month - 1 - KEEP_FULL_MONTHS
    return datetime(months // 12, months % 12 + 1, 1, tzinfo=dt_timezone.utc)


def _month_range(month):
    """The first moment (UTC) of a month and of the one after it, from its first day."""
    start = datetime(month.year, month.month, 1, tzinfo=dt_timezone.utc)
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return start, datetime(following.year, following.month, 1, tzinfo=dt_timezone.utc)


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


class Command(BaseCommand):
    help = (
        "Write streams that finished before the retention window - the current month and"
        f" the {KEEP_FULL_MONTHS} full months before it - to one Parquet file per month in"
        " ARCHIVE_DIR/streams, recording each month in ArchivedMonth. Months already"
        " recorded are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Archive just this month (YYYY-MM), e.g. to work through a backlog one month at a time.",
        )

    def handle(self, *args, **options):
        started = time.monotonic()
        cutoff = retention_start(timezone.now())
        streams = Stream.objects.filter(finished_at__lt=cutoff).exclude(status=Stream.Status.LIVE)

        if options["month"]:
            month = self._parse_month(options["month"], cutoff)
            if ArchivedMonth.objects.filter(month=month).exists():
                self.stdout.write(f"{month:%Y-%m} is archived already.")
                return
            month_start, month_end = _month_range(month)
            streams = streams.filter(finished_at__gte=month_start, finished_at__lt=month_end)

        for archived_month in ArchivedMonth.objects.values_list("month", flat=True):
            month_start, month_end = _month_range(archived_month)
            streams = streams.exclude(finished_at__gte=month_start, finished_at__lt=month_end)

        directory = Path(settings.ARCHIVE_DIR) / "streams"
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
        self.stdout.write(f"Done in {timedelta(seconds=round(time.monotonic() - started))}.")

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

        sha256 = self._sha256(month_file.partial_path)
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
        self.stdout.write(
            f"Archived {archived_month.month:%Y-%m}: {archived_month.streams_count:,} streams"
            f" (ids {archived_month.first_stream_id}-{archived_month.last_stream_id}),"
            f" {archived_month.file_size / 1024 ** 2:,.1f} MB -> {month_file.path}"
        )

    @staticmethod
    def _parse_month(raw, cutoff):
        try:
            month = datetime.strptime(raw, "%Y-%m").date()
        except ValueError:
            raise CommandError(f"--month takes YYYY-MM, not {raw!r}.") from None
        if _month_range(month)[0] >= cutoff:
            raise CommandError(
                f"{raw} is inside the retention window, which starts {cutoff:%Y-%m-%d};"
                " only earlier months are archived."
            )
        return month

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
