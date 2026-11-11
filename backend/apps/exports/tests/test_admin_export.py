"""Tests for exporting the newest export records from the admin, as a CSV file."""

import csv
import io
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.exports.models import Export
from apps.userlists.models import UserListOfStreamers

User = get_user_model()


class ExportRecordsExportTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))
        self.user = User.objects.create_user(username="dev")
        self.list = UserListOfStreamers.objects.create(owner=self.user, title="secret plans")

    def _record(self, when, **fields):
        export = Export.objects.create(user=self.user, **fields)
        Export.objects.filter(pk=export.pk).update(created_at=when)

    def test_numbers_each_users_exports_and_gives_a_list_by_its_number(self):
        self._record(
            datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
            source=Export.Source.LIST, list_of_streamers=self.list, file_format="xlsx", rows=12,
        )
        self._record(
            datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
            source=Export.Source.SEARCH, file_format="csv", rows=5000,
            search_filters={"lang": "en", "peak": "51-200", "genres": "any"},
        )

        response = self.client.get(reverse("admin:exports_export_export"))
        header, newest, first = csv.reader(io.StringIO(response.content.decode()))

        self.assertEqual(header, [
            "user", "exported_at_utc", "export_number", "days_since_previous_export",
            "source", "list", "file_format", "rows", "search",
        ])
        self.assertEqual(newest, [
            str(self.user.pk), "2026-10-03 12:00", "2", "2.0", "search", "", "csv", "5000", "lang=en peak=51-200",
        ])
        self.assertEqual(first[2:6], ["1", "", "list", str(self.list.pk)])
        self.assertNotContains(response, "secret plans")

    def test_the_list_offers_the_export_beside_the_graphs(self):
        response = self.client.get(reverse("admin:exports_export_changelist"))

        self.assertContains(response, f'href="{reverse("admin:exports_export_graphs")}"')
        self.assertContains(response, f'action="{reverse("admin:exports_export_export")}"')
