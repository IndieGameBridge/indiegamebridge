"""Tests for exporting the newest fetch runs from the admin, as a CSV file."""

import csv
import io
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.fetch.models import FetchRun, FetchRunLanguage

User = get_user_model()


class FetchRunExportTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

    def test_adds_up_each_runs_languages(self):
        run = FetchRun.objects.create(
            started_at=datetime(2026, 11, 10, 8, 40, tzinfo=UTC), duration_seconds=180.04,
            status=FetchRun.Status.SUCCEEDED, finalize_seconds=5.0,
            streams_collected=100, streams_finalized=40, streams_dropped=7,
        )
        FetchRunLanguage.objects.create(run=run, language="en", requests=50, helix_seconds=10.0, write_seconds=60.0)
        FetchRunLanguage.objects.create(run=run, language="de", requests=8, helix_seconds=2.5, write_seconds=7.0)

        response = self.client.get(reverse("admin:fetch_fetchrun_export"))
        header, row = csv.reader(io.StringIO(response.content.decode()))

        self.assertEqual(dict(zip(header, row)), {
            "started_at_utc": "2026-11-10 08:40", "status": "succeeded", "duration_seconds": "180.0",
            "time_limit_hit": "no", "languages": "2", "requests": "58", "helix_seconds": "12.5",
            "write_seconds": "67.0", "streams_collected": "100", "streams_finalized": "40",
            "streams_dropped": "7", "finalize_seconds": "5.0", "error": "",
        })
