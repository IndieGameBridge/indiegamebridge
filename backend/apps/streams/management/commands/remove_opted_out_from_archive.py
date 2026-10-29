"""Remove the streams of streamers who opted out from the archived months' files.

Opting out deletes a streamer's profile, and their streams in Postgres with it, but the
months archive_streams wrote earlier still hold them. This rewrites each file that does,
without them, and updates the month's record - count, ids, size, SHA-256 - so
delete_archived_streams keeps accepting the file. A file with nothing to remove has one
column read, and is left as it is.

Opt-outs stay in TwitchExclusion, so every run checks the files against all of them, and
whatever a failed run left is picked up by the next one. Copies of a file made before it
was rewritten still hold the removed streams; copy it again.
"""

import os
import time
from datetime import timedelta

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.streams.archive import archive_lock, file_problem, files_dir, sha256_of
from apps.streams.models import ArchivedMonth
from apps.users.models import TwitchExclusion


class Command(BaseCommand):
    help = (
        "Remove the streams of streamers who opted out from the archived months' files,"
        " rewriting only the files that hold any, and update each rewritten month's record."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be removed, without rewriting anything.",
        )

    def handle(self, *args, **options):
        with archive_lock() as locked:
            if not locked:
                self.stdout.write("Another archive run is in progress; not starting.")
                return
            self._remove(options["dry_run"])

    def _remove(self, dry_run):
        started = time.monotonic()
        opted_out = pa.array(TwitchExclusion.objects.values_list("twitch_id", flat=True), type=pa.int64())
        months_found = 0
        for archived_month in ArchivedMonth.objects.order_by("month"):
            label = f"{archived_month.month:%Y-%m}"
            path = files_dir() / archived_month.file_name
            if not path.exists():
                raise CommandError(f"{label}: its file {path} is missing.")

            host_user_ids = pq.read_table(path, columns=["host_user_id"]).column("host_user_id")
            matches = pc.is_in(host_user_ids, value_set=opted_out)
            removing = pc.sum(matches).as_py() or 0
            if not removing:
                continue
            months_found += 1
            streamers = len(pc.unique(host_user_ids.filter(matches)))
            if dry_run:
                self.stdout.write(f"{label}: would remove {removing:,} streams of {streamers:,} opted-out streamers.")
                continue

            # Rewriting a file that isn't the archived one would make its record vouch for it.
            problem = file_problem(archived_month, path)
            if problem:
                raise CommandError(f"{label}: {problem}; left as it is.")
            self._rewrite(archived_month, path, opted_out)
            self.stdout.write(
                f"Rewrote {label}: removed {removing:,} streams of {streamers:,} opted-out streamers;"
                f" {archived_month.streams_count:,} left, {archived_month.file_size / 1024 ** 2:,.1f} MB."
                f" Copies of {archived_month.file_name} made before now still hold them; copy it again."
            )

        if not months_found:
            self.stdout.write(
                f"Nothing to remove: no archived month holds streams of the {len(opted_out):,}"
                " streamers who opted out."
            )
            return
        self.stdout.write(f"Done in {timedelta(seconds=round(time.monotonic() - started))}.")

    @staticmethod
    def _rewrite(archived_month, path, opted_out):
        """Write the file again without the opted-out streamers' streams, a row group at a
        time, under a .partial name until it checks out; then record what it holds."""
        partial_path = path.with_name(f"{path.name}.partial")
        kept = 0
        first_stream_id = last_stream_id = None
        try:
            with pq.ParquetFile(path) as source, pq.ParquetWriter(
                partial_path, source.schema_arrow, compression="zstd",
            ) as writer:
                for index in range(source.num_row_groups):
                    row_group = source.read_row_group(index)
                    row_group = row_group.filter(
                        pc.invert(pc.is_in(row_group.column("host_user_id"), value_set=opted_out))
                    )
                    if not row_group.num_rows:
                        continue
                    writer.write_table(row_group)
                    kept += row_group.num_rows
                    ids = pc.min_max(row_group.column("id")).as_py()
                    first_stream_id = ids["min"] if first_stream_id is None else min(first_stream_id, ids["min"])
                    last_stream_id = ids["max"] if last_stream_id is None else max(last_stream_id, ids["max"])

            with pq.ParquetFile(partial_path) as written:
                rows_in_file = written.metadata.num_rows
            if rows_in_file != kept:
                raise CommandError(
                    f"{archived_month.month:%Y-%m}: the rewritten file holds {rows_in_file:,} rows,"
                    f" but {kept:,} streams were written to it; the old file was left in place."
                )
            sha256 = sha256_of(partial_path)
        except BaseException:
            partial_path.unlink(missing_ok=True)
            raise

        os.replace(partial_path, path)
        archived_month.streams_count = kept
        # A month left with no streams keeps its old ids; they still bound its walk in Postgres.
        if first_stream_id is not None:
            archived_month.first_stream_id = first_stream_id
            archived_month.last_stream_id = last_stream_id
        archived_month.file_size = path.stat().st_size
        archived_month.sha256 = sha256
        archived_month.rewritten_at = timezone.now()
        archived_month.save(update_fields=[
            "streams_count", "first_stream_id", "last_stream_id", "file_size", "sha256", "rewritten_at",
        ])
