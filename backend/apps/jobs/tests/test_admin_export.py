"""Tests for exporting the newest job runs from the admin, as a CSV file."""

import csv
import io
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.jobs.models import JobRun

User = get_user_model()


class JobRunExportTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

    def test_writes_each_run_with_its_counts_and_what_failed(self):
        JobRun.objects.create(
            job="rebuild_search_stats", arguments="", status=JobRun.Status.SUCCEEDED,
            started_at=datetime(2026, 11, 10, 6, 5, tzinfo=UTC), duration_seconds=312.44,
            counts={"deleted": 3, "rows": 1200, "written": 40}, output="pages of output", error="",
        )
        JobRun.objects.create(
            job="archive_streams", arguments="--month 2026-07", status=JobRun.Status.FAILED,
            started_at=datetime(2026, 11, 10, 10, 27, tzinfo=UTC), duration_seconds=1.0,
            counts={}, output="", error="Traceback (most recent call last):\nValueError: bad month",
        )

        response = self.client.get(reverse("admin:jobs_jobrun_export"))
        header, failed, succeeded = csv.reader(io.StringIO(response.content.decode()))

        self.assertEqual(header, ["job", "arguments", "status", "started_at_utc", "duration_seconds", "counts", "error"])
        self.assertEqual(failed, [
            "archive_streams", "'--month 2026-07", "failed", "2026-11-10 10:27", "1.0", "", "ValueError: bad month",
        ])
        # In the order the job declares its counts, as the list's "What it did" shows them.
        self.assertEqual(succeeded[4:6], ["312.4", "rows=1200; written=40; deleted=3"])
        self.assertNotContains(response, "pages of output")

    def test_the_list_keeps_its_busy_time_link_and_offers_the_export(self):
        response = self.client.get(reverse("admin:jobs_jobrun_changelist"))

        self.assertContains(response, f'href="{reverse("admin:jobs_jobrun_busy_time")}"')
        self.assertContains(response, f'action="{reverse("admin:jobs_jobrun_export")}"')
