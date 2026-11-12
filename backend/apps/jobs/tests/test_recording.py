"""Tests for RecordedCommand: each run of a scheduled command becomes a JobRun."""

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import SimpleTestCase, TestCase

from apps.jobs.cron import every_text
from apps.jobs.models import JobRun
from apps.jobs.recording import MAX_OUTPUT, RecordedCommand, _kept
from apps.pages.management.commands.update_cached_pages import Command as UpdateCachedPages


class _Counting(RecordedCommand):
    def handle(self, *args, **options):
        self.seen_while_running = JobRun.objects.get().status
        self.count(streams=2)
        self.count(streams=3, months=1)
        self.stdout.write(self.style.SUCCESS("Done."))


class RecordedCommandTests(TestCase):
    def test_records_the_run_its_counts_and_what_it_printed(self):
        out = StringIO()
        command = _Counting()

        call_command(command, stdout=out, no_color=True)

        run = JobRun.objects.get()
        self.assertEqual(run.job, "test_recording")
        self.assertEqual(run.status, JobRun.Status.SUCCEEDED)
        self.assertGreaterEqual(run.duration_seconds, 0)
        self.assertEqual(run.finished_at, run.started_at + timedelta(seconds=run.duration_seconds))
        self.assertEqual(run.counts, {"streams": 5, "months": 1})
        self.assertEqual(run.output, "Done.\n")
        # What it printed still reaches its own output.
        self.assertEqual(out.getvalue(), "Done.\n")
        # The row is there from the start, so a run that's killed still shows up.
        self.assertEqual(command.seen_while_running, JobRun.Status.RUNNING)

    def test_a_scheduled_command_records_its_own_counts(self):
        call_command("delete_expired_personal_data", stdout=StringIO())

        run = JobRun.objects.get()
        self.assertEqual(run.job, "delete_expired_personal_data")
        self.assertEqual(run.counts, {"sign_ins": 0, "contact_messages": 0, "exports": 0, "searches": 0})
        self.assertTrue(run.output.startswith("Deleted personal data from before "))

    def test_a_failed_run_keeps_its_error(self):
        with self.assertRaises(CommandError):
            call_command("update_cached_pages", "nope", stdout=StringIO())

        run = JobRun.objects.get()
        self.assertEqual(run.status, JobRun.Status.FAILED)
        self.assertTrue(run.error.startswith("CommandError: Unknown page key(s): nope."))
        self.assertIsNotNone(run.duration_seconds)

    def test_a_dry_run_is_not_recorded(self):
        call_command("delete_expired_personal_data", dry_run=True, stdout=StringIO())

        self.assertFalse(JobRun.objects.exists())

    def test_keeps_the_arguments_it_was_run_with(self):
        command = UpdateCachedPages(stdout=StringIO(), stderr=StringIO())

        # manage.py closes the connections when the command ends; the test still needs its own.
        with mock.patch.object(connections, "close_all"), self.assertRaises(SystemExit):
            command.run_from_argv(["manage.py", "update_cached_pages", "nope", "--verbosity", "2"])

        self.assertEqual(JobRun.objects.get().arguments, "nope --verbosity 2")


class KeptOutputTests(SimpleTestCase):
    def test_drops_the_terminal_colors(self):
        self.assertEqual(_kept("\x1b[32;1mApproved 3 streams.\x1b[0m\n"), "Approved 3 streams.\n")

    def test_keeps_the_end_of_a_long_output(self):
        kept = _kept("x" * MAX_OUTPUT + "the summary")

        self.assertEqual(len(kept), MAX_OUTPUT + 1)
        self.assertTrue(kept.startswith("…"))
        self.assertTrue(kept.endswith("the summary"))


class EveryTextTests(SimpleTestCase):
    def test_names_the_usual_schedules(self):
        self.assertEqual(
            [every_text(every) for every in (
                timedelta(minutes=20), timedelta(hours=1), timedelta(hours=6), timedelta(days=1),
                timedelta(weeks=1), timedelta(days=35), timedelta(days=3), None,
            )],
            ["Every 20 min", "Hourly", "Every 6 h", "Daily", "Weekly", "Monthly", "Every 3 days", "No schedule"],
        )
