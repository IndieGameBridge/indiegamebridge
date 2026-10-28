"""Tests for delete_expired_personal_data: what goes after the retention period, and what stays."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.contact.models import ContactMessage
from apps.exports.models import Export
from apps.users.management.commands.delete_expired_personal_data import RETENTION
from apps.users.models import LoginSnapshot

User = get_user_model()


class DeleteExpiredPersonalDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dev")
        now = timezone.now()
        self.expired_at = now - RETENTION - timedelta(days=1)
        self.kept_at = now - RETENTION + timedelta(days=1)
        for created_at in (self.expired_at, self.kept_at):
            self._make_records(created_at)

    def _make_records(self, created_at):
        records = (
            LoginSnapshot.objects.create(user=self.user, ip_address="203.0.113.7"),
            ContactMessage.objects.create(name="Dev", email="dev@example.com", message="Hello"),
            Export.objects.create(
                user=self.user, source=Export.Source.SEARCH, file_format=Export.FileFormat.CSV, rows=1,
            ),
        )
        for record in records:
            # auto_now_add overrides a created_at passed to create(), so backdate after.
            type(record).objects.filter(pk=record.pk).update(created_at=created_at)

    def _run(self, *args):
        out = StringIO()
        call_command("delete_expired_personal_data", *args, stdout=out)
        return out.getvalue()

    def test_deletes_what_is_past_the_retention_period_and_keeps_the_rest(self):
        output = self._run()

        for model in (LoginSnapshot, ContactMessage, Export):
            with self.subTest(model=model.__name__):
                self.assertEqual(list(model.objects.values_list("created_at", flat=True)), [self.kept_at])
        self.assertIn("Deleted personal data from before", output)
        self.assertIn("1 sign-in records, 1 contact messages, 1 export records", output)

    def test_a_dry_run_only_counts(self):
        output = self._run("--dry-run")

        for model in (LoginSnapshot, ContactMessage, Export):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), 2)
        self.assertIn("Would delete personal data from before", output)
        self.assertIn("1 sign-in records, 1 contact messages, 1 export records", output)

    def test_a_run_with_nothing_expired_deletes_nothing(self):
        for model in (LoginSnapshot, ContactMessage, Export):
            model.objects.filter(created_at=self.expired_at).delete()

        output = self._run()

        self.assertIn("0 sign-in records, 0 contact messages, 0 export records", output)
        self.assertEqual(LoginSnapshot.objects.count(), 1)
