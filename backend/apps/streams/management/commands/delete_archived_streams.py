"""Delete from Postgres the streams of months archive_streams has written to files.

Works through the archived months whose streams are still in Postgres, oldest first.
A month is touched only if its file is still the one archive_streams wrote - same size,
same SHA-256 - and each batch is checked against the ids in that file before it's
deleted, so no stream leaves Postgres without being in its month's file.

The deletes go in small batches with short pauses between them, so the fetch and the
site carry on alongside. --max-streams ends a run early, and the next run carries on
from the lowest id still left. Postgres reuses the freed space for new streams once
autovacuum has been through the table.
"""

import bisect
import time
from datetime import timedelta

import pyarrow.compute as pc
import pyarrow.parquet as pq
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min
from django.utils import timezone

from apps.streams.archive import archive_lock, files_dir, month_range, parse_month, sha256_of
from apps.streams.models import ArchivedMonth, Stream

# Ids covered by one batch. Ids run about three to every stream kept - low-viewer
# streams take ids too, and are dropped - so a batch is around 15-20k streams.
BATCH_IDS = 50000

# Between batches, so the deletes come in short bursts the fetch and the site work between.
PAUSE_SECONDS = 0.5


class Command(BaseCommand):
    help = (
        "Delete from Postgres the streams of months archive_streams has written to files,"
        " oldest month first, after checking each file against its record and each batch"
        " against the file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Delete just this archived month's streams (YYYY-MM).",
        )
        parser.add_argument(
            "--max-streams",
            type=int,
            help="Stop once about this many streams are deleted; the next run carries on from there.",
        )

    def handle(self, *args, **options):
        with archive_lock() as locked:
            if not locked:
                self.stdout.write("Another archive run is in progress; not starting.")
                return
            self._delete(options["month"], options["max_streams"])

    def _delete(self, raw_month, max_streams):
        started = time.monotonic()
        archived_months = ArchivedMonth.objects.filter(rows_deleted_at__isnull=True).order_by("month")
        if raw_month:
            archived_months = archived_months.filter(month=parse_month(raw_month))
        archived_months = list(archived_months)
        if not archived_months:
            self.stdout.write("Nothing to delete: no archived month has streams left in Postgres.")
            return

        deleted = 0
        for archived_month in archived_months:
            budget = None if max_streams is None else max_streams - deleted
            if budget is not None and budget <= 0:
                self.stdout.write("Stopped at --max-streams; run again to carry on.")
                break
            deleted_now, finished = self._delete_month(archived_month, budget)
            deleted += deleted_now
            if not finished:
                break
        self.stdout.write(f"Done in {timedelta(seconds=round(time.monotonic() - started))}.")

    def _delete_month(self, archived_month, budget):
        """Delete one archived month's streams, stopping once budget of them are gone.

        Returns how many were deleted, and whether the month is out of Postgres now.
        """
        label = f"{archived_month.month:%Y-%m}"
        path = files_dir() / archived_month.file_name
        self._check_file(archived_month, path, label)
        file_ids = self._sorted_ids(path)

        month_start, month_end = month_range(archived_month.month)
        streams = Stream.objects.filter(
            finished_at__gte=month_start,
            finished_at__lt=month_end,
            id__lte=archived_month.last_stream_id,
        ).exclude(status=Stream.Status.LIVE)

        # The month's first id, or where a run stopped by --max-streams left off.
        low = streams.filter(id__gte=archived_month.first_stream_id).aggregate(low=Min("id"))["low"]
        deleted = 0
        if low is not None:
            for window_start in range(low, archived_month.last_stream_id + 1, BATCH_IDS):
                window_end = window_start + BATCH_IDS
                ids = list(
                    streams.filter(id__gte=window_start, id__lt=window_end).values_list("id", flat=True)
                )
                if not ids:
                    continue
                not_in_file = set(ids) - self._ids_between(file_ids, window_start, window_end)
                if not_in_file:
                    raise CommandError(
                        f"{label}: {len(not_in_file):,} of its streams in Postgres aren't in its file"
                        f" (id {min(not_in_file)}, for one); stopped before deleting them."
                    )
                count, _ = Stream.objects.filter(id__in=ids).delete()
                deleted += count
                if budget is not None and deleted >= budget:
                    self.stdout.write(
                        f"{label}: deleted {deleted:,} streams, then stopped at --max-streams;"
                        " run again to carry on."
                    )
                    return deleted, False
                time.sleep(PAUSE_SECONDS)

        archived_month.rows_deleted_at = timezone.now()
        archived_month.save(update_fields=["rows_deleted_at"])
        self.stdout.write(f"Deleted {label}: {deleted:,} streams this run; the month is out of Postgres.")
        return deleted, True

    @staticmethod
    def _check_file(archived_month, path, label):
        """Refuse a month whose file isn't the one archive_streams wrote."""
        if not path.exists():
            raise CommandError(f"{label}: its file {path} is missing; its streams were left in place.")
        if path.stat().st_size != archived_month.file_size or sha256_of(path) != archived_month.sha256:
            raise CommandError(
                f"{label}: {path} isn't the file archive_streams wrote - its size or SHA-256"
                " differs; its streams were left in place."
            )

    @staticmethod
    def _sorted_ids(path):
        """The ids of the streams in a month's file, in ascending order."""
        ids = pq.read_table(path, columns=["id"]).column("id").combine_chunks()
        return ids.take(pc.sort_indices(ids))

    @staticmethod
    def _ids_between(sorted_ids, low, high):
        """The file's ids from low up to, but not including, high."""
        start = bisect.bisect_left(sorted_ids, low, key=lambda scalar: scalar.as_py())
        end = bisect.bisect_left(sorted_ids, high, key=lambda scalar: scalar.as_py())
        return set(sorted_ids.slice(start, end - start).to_pylist())
