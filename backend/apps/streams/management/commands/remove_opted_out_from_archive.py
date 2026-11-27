"""Remove the streams of streamers who opted out from the archived months' files, now.

archive_streams does this every Monday; this runs it by hand, or counts what it would
remove with --dry-run. What it does is described in apps.streams.archive_cleanup.
"""

import time
from datetime import timedelta

from apps.jobs.recording import RecordedCommand
from apps.streams.archive import archive_lock
from apps.streams.archive_cleanup import remove_opted_out


class Command(RecordedCommand):
    help = (
        "Remove the streams of streamers who opted out from the archived months' files,"
        " rewriting only the files that hold any, and update each rewritten month's record."
        " archive_streams does this every Monday."
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
            started = time.monotonic()
            months, streams = remove_opted_out(self.stdout.write, dry_run=options["dry_run"])
            if months and not options["dry_run"]:
                self.count(months=months, streams=streams)
                self.stdout.write(f"Done in {timedelta(seconds=round(time.monotonic() - started))}.")
