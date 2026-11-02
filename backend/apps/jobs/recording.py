"""RecordedCommand, the base of the scheduled management commands: each run becomes a
JobRun, which the admin's Job runs pages show."""

import io
import re
import shlex
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.jobs.models import JobRun

# What a run printed is kept up to this long, from its end, where the summary is.
MAX_OUTPUT = 20_000

# The colors a command's styles add when it prints to a terminal.
_COLOR_CODES = re.compile(r"\x1b\[[0-9;]*m")


class _Tee:
    """An output stream that copies what's written to it into a buffer as well."""

    def __init__(self, out, copy):
        self._out = out
        self._copy = copy

    def write(self, text):
        self._copy.write(text)
        return self._out.write(text)

    def __getattr__(self, name):
        return getattr(self._out, name)


def _kept(printed):
    printed = _COLOR_CODES.sub("", printed)
    return printed if len(printed) <= MAX_OUTPUT else "…" + printed[-MAX_OUTPUT:]


class RecordedCommand(BaseCommand):
    """A management command that records each run as a JobRun: when it ran, how long it
    took, whether it failed, what it printed, and what it did, as the counts it adds up
    with count(). A --dry-run isn't recorded: it changes nothing."""

    # What followed the command's name in manage.py's arguments; call_command has none.
    arguments = ""

    def run_from_argv(self, argv):
        self.arguments = shlex.join(argv[2:])
        super().run_from_argv(argv)

    def count(self, **amounts):
        """Add to what the run has done, as in self.count(approved=12, deleted=3)."""
        self.counts.update(amounts)

    def execute(self, *args, **options):
        self.counts = Counter()
        if options.get("dry_run"):
            return super().execute(*args, **options)

        printed = io.StringIO()
        options["stdout"] = _Tee(options.get("stdout") or self.stdout._out, printed)
        run = JobRun.objects.create(
            job=self.__module__.rsplit(".", 1)[-1],
            arguments=self.arguments[:255],
            started_at=timezone.now(),
        )
        try:
            return super().execute(*args, **options)
        except BaseException as exc:
            run.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            run.counts = dict(self.counts)
            run.output = _kept(printed.getvalue())
            run.finish()
