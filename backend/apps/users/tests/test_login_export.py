"""Tests for exporting the newest login snapshots from the admin, as a CSV file."""

import csv
import io
from datetime import UTC, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.users.models import LoginSnapshot

User = get_user_model()

HEADER = [
    "user", "logged_in_at_utc", "login_number", "days_since_previous_login", "user_joined_utc", "country", "staff",
]


class LoginExportTests(TestCase):
    def setUp(self):
        self.url = reverse("admin:users_loginsnapshot_export")
        self.admin = User.objects.create_superuser(username="admin", password="unused")
        self.client.force_login(self.admin)
        # Logging in records a snapshot of its own; start from none.
        LoginSnapshot.objects.all().delete()
        self.alice = User.objects.create_user(username="alice")
        User.objects.filter(pk=self.alice.pk).update(date_joined=datetime(2026, 9, 1, 10, 0, tzinfo=UTC))

    def _login(self, user, when, country="DE"):
        snapshot = LoginSnapshot.objects.create(
            user=user, ip_address="203.0.113.7", country_code=country, region="Bavaria", city="Munich",
        )
        LoginSnapshot.objects.filter(pk=snapshot.pk).update(created_at=when)

    def _export(self, **params):
        response = self.client.get(self.url, params)
        return response, list(csv.reader(io.StringIO(response.content.decode())))

    def test_numbers_each_users_logins_and_the_days_between_them(self):
        self._login(self.alice, datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
        self._login(self.alice, datetime(2026, 10, 15, 21, 0, tzinfo=UTC))

        _, (header, newest, first) = self._export()

        self.assertEqual(header, HEADER)
        self.assertEqual(newest, [str(self.alice.pk), "2026-10-15 21:00", "2", "14.5", "2026-09-01 10:00", "DE", "no"])
        self.assertEqual(first[1:4], ["2026-10-01 09:00", "1", ""])

    def test_counts_logins_older_than_the_file_too(self):
        for day in (1, 2, 3):
            self._login(self.alice, datetime(2026, 10, day, tzinfo=UTC))

        with mock.patch("core.utils.admin_export.EXPORT_SIZES", (1, 2)):
            _, rows = self._export(rows=1)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1:4], ["2026-10-03 00:00", "3", "1.0"])

    def test_holds_the_newest_logins_up_to_the_size_picked(self):
        for day in (1, 2, 3):
            self._login(self.alice, datetime(2026, 10, day, tzinfo=UTC))

        with mock.patch("core.utils.admin_export.EXPORT_SIZES", (1, 2)):
            _, rows = self._export(rows=2)

        self.assertEqual([row[1] for row in rows[1:]], ["2026-10-03 00:00", "2026-10-02 00:00"])

    def test_leaves_out_ips_names_and_places_finer_than_a_country(self):
        self._login(self.alice, datetime(2026, 10, 1, tzinfo=UTC))

        response, _ = self._export()

        for private in ("203.0.113.7", "alice", "Bavaria", "Munich"):
            self.assertNotContains(response, private)

    def test_marks_staff_logins(self):
        self._login(self.admin, datetime(2026, 10, 1, tzinfo=UTC))

        _, (_, row) = self._export()

        self.assertEqual(row[-1], "yes")

    def test_downloads_as_a_dated_csv_file_no_cache_keeps(self):
        response, _ = self._export(rows=300)

        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertRegex(
            response["Content-Disposition"],
            r'^attachment; filename="indiegamebridge-logins-last-300-\d{4}-\d{2}-\d{2}\.csv"$',
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_the_list_offers_the_sizes(self):
        response = self.client.get(reverse("admin:users_loginsnapshot_changelist"))

        self.assertContains(response, f'action="{self.url}"')
        self.assertContains(response, '<option value="100">100</option>')
        self.assertContains(response, '<option value="1000">1000</option>')

    def test_needs_a_staff_login_that_may_view_logins(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

        self.client.force_login(User.objects.create_user(username="staff", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)
