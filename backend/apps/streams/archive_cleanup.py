"""Remove the streams of streamers who opted out from the archived months' files.

Opting out deletes a streamer's profile, and their streams in Postgres with it, but the
month files written earlier still hold them. This rewrites each file that does, without
them, and updates the month's record - count, ids, size, SHA-256 - so the archive keeps
accepting the file, and so the month's game history is counted again from it. A file with
nothing to remove has one column read, and is left as it is.

Opt-outs stay in TwitchExclusion, so every run checks the files against all of them, and
whatever a failed run left is picked up by the next one. Copies of a file made before it
was rewritten still hold the removed streams; copy it again.

archive_streams runs this on Mondays; remove_opted_out_from_archive runs it by hand.
"""

import os

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from django.core.management.base import CommandError
from django.utils import timezone

from apps.streams.archive import file_problem, files_dir, sha256_of
from apps.streams.models import ArchivedMonth
from apps.users.models import TwitchExclusion


def remove_opted_out(write, dry_run=False):
    """Rewrite every month file that holds opted-out streamers without them, saying what
    it did through `write`. Returns how many files it rewrote, and how many streams it
    removed from them; with dry_run, how many it would have."""
    opted_out = pa.array(TwitchExclusion.objects.values_list("twitch_id", flat=True), type=pa.int64())
    rewritten = removed = 0
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
        streamers = len(pc.unique(host_user_ids.filter(matches)))
        rewritten += 1
        removed += removing
        if dry_run:
            write(f"{label}: would remove {removing:,} streams of {streamers:,} opted-out streamers.")
            continue

        # Rewriting a file that isn't the archived one would make its record vouch for it.
        problem = file_problem(archived_month, path)
        if problem:
            raise CommandError(f"{label}: {problem}; left as it is.")
        _rewrite(archived_month, path, opted_out)
        write(
            f"Rewrote {label}: removed {removing:,} streams of {streamers:,} opted-out streamers;"
            f" {archived_month.streams_count:,} left, {archived_month.file_size / 1024 ** 2:,.1f} MB."
            f" Copies of {archived_month.file_name} made before now still hold them; copy it again."
        )

    if not rewritten:
        write(
            f"Nothing to remove: no archived month holds streams of the {len(opted_out):,}"
            " streamers who opted out."
        )
    return rewritten, removed


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
    # A month left with no streams keeps its old ids; they still bound the check for
    # streams of it left in Postgres.
    if first_stream_id is not None:
        archived_month.first_stream_id = first_stream_id
        archived_month.last_stream_id = last_stream_id
    archived_month.file_size = path.stat().st_size
    archived_month.sha256 = sha256
    archived_month.rewritten_at = timezone.now()
    archived_month.save(update_fields=[
        "streams_count", "first_stream_id", "last_stream_id", "file_size", "sha256", "rewritten_at",
    ])
