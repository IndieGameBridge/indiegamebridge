import logging
import time

from django.core.management.base import BaseCommand
from django.db import connection, transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "One-shot backfill: populates Stream.avg_viewers for already-finalized"
        " streams (OFFLINE and APPROVED) created before the field existed."
        " avg_viewers = mean of the per-snapshot viewer counts, rounded - the"
        " same value fetch_twitch_streams now computes at finalization."
        " Snapshots are retained on finalized streams, so this reads them back"
        " out of the JSONB column. Streams whose snapshots are empty/missing"
        " are left at 0 (they carry no usable signal)."
        "\n\n"
        "Processes streams in id-range batches, each in its own transaction, to"
        " keep memory bounded and lock duration short on resource-constrained"
        " hosts over a multi-million row table. Safe to re-run (idempotent)."
        " Use --start-id to resume from a specific id if a previous run was"
        " interrupted."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many finalized streams would change without writing."
                " Same batched scan as the real run.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Stream id range per batch. Default 5000. Smaller values reduce"
                " memory and lock pressure but add per-statement overhead.",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            default=None,
            help="Skip ids below this value. Use to resume after a partial run."
                " Default: start from MIN(id) of finalized streams.",
        )
        parser.add_argument(
            "--stop-id",
            type=int,
            default=None,
            help="Stop processing at this id (inclusive). Default: MAX(id) of"
                " finalized streams.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.0,
            help="Seconds to pause between batches (default: 0.0). Raise to ease"
                " load on the live database.",
        )

    # Per-batch aggregation. `%s` placeholders are (lo, hi). The inner
    # `s.id BETWEEN ...` keeps the unnest + group-by scoped to one id slice
    # instead of aggregating the whole table per batch. Only finalized streams
    # with a non-empty snapshot array contribute; everything else keeps its
    # default of 0.
    _SUBQUERY_SQL = """
        SELECT s.id AS stream_id,
               ROUND(AVG((elem->>'v')::numeric))::int AS avg_v
        FROM streams_stream s,
             LATERAL jsonb_array_elements(s.snapshots) elem
        WHERE s.status IN ('offline', 'approved')
          AND s.id BETWEEN %s AND %s
          AND jsonb_typeof(s.snapshots) = 'array'
          AND jsonb_array_length(s.snapshots) > 0
        GROUP BY s.id
    """

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        batch_size = options["batch_size"]
        start_id_arg = options.get("start_id")
        stop_id_arg = options.get("stop_id")
        sleep_seconds = options["sleep"]

        if batch_size <= 0:
            self.stderr.write("--batch-size must be > 0.")
            return

        bounds = self._finalized_id_bounds()
        if bounds is None:
            self.stdout.write("No finalized streams to process.")
            return
        min_id, max_id = bounds

        lo = start_id_arg if start_id_arg is not None else min_id
        hi_limit = stop_id_arg if stop_id_arg is not None else max_id

        if lo > hi_limit:
            self.stdout.write(
                f"start-id ({lo}) > stop-id ({hi_limit}); nothing to do."
            )
            return

        self.stdout.write(
            f"{'DRY RUN ' if dry_run else ''}Backfilling Stream.avg_viewers over"
            f" id range [{lo}, {hi_limit}] in batches of {batch_size}..."
        )

        total_changed = 0
        batches = 0
        started_at = time.monotonic()

        while lo <= hi_limit:
            hi = min(lo + batch_size - 1, hi_limit)
            changed = self._process_batch(lo, hi, dry_run=dry_run)
            total_changed += changed
            batches += 1

            elapsed = time.monotonic() - started_at
            self.stdout.write(
                f"  batch {batches:>4d} [{lo}..{hi}]:"
                f" {changed} {'would change' if dry_run else 'updated'}"
                f"  (total: {total_changed}; elapsed: {elapsed:.1f}s)"
            )
            lo = hi + 1

            if sleep_seconds > 0 and lo <= hi_limit:
                time.sleep(sleep_seconds)

        msg = (
            f"DRY RUN: would update {total_changed} finalized streams"
            f" across {batches} batches."
            if dry_run else
            f"Backfilled avg_viewers for {total_changed} finalized streams"
            f" across {batches} batches."
        )
        self.stdout.write(self.style.SUCCESS(msg))

    @staticmethod
    def _finalized_id_bounds():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT MIN(id), MAX(id) FROM streams_stream"
                " WHERE status IN ('offline', 'approved');"
            )
            min_id, max_id = cur.fetchone()
        if min_id is None:
            return None
        return min_id, max_id

    def _process_batch(self, lo, hi, dry_run):
        """One id-range batch, in its own transaction. Returns row count."""
        with transaction.atomic():
            with connection.cursor() as cur:
                if dry_run:
                    cur.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM ({self._SUBQUERY_SQL}) sub
                        JOIN streams_stream s ON s.id = sub.stream_id
                        WHERE s.avg_viewers IS DISTINCT FROM sub.avg_v;
                        """,
                        [lo, hi],
                    )
                    (count,) = cur.fetchone()
                    return count

                cur.execute(
                    f"""
                    UPDATE streams_stream s
                    SET avg_viewers = sub.avg_v
                    FROM ({self._SUBQUERY_SQL}) sub
                    WHERE s.id = sub.stream_id
                      AND s.avg_viewers IS DISTINCT FROM sub.avg_v;
                    """,
                    [lo, hi],
                )
                return cur.rowcount
