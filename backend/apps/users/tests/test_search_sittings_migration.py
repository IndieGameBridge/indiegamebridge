"""Tests for migration 0006: the stored searches turn into sittings and lose their user."""

from datetime import UTC, datetime, timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("users", "0005_searchsnapshot")]
AFTER = [("users", "0006_searchsnapshot_sittings")]


class SearchSittingsMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        User = old_apps.get_model("users", "User")
        Search = old_apps.get_model("users", "SearchSnapshot")
        alice = User.objects.create(username="alice")
        staff = User.objects.create(username="staff", is_staff=True)
        start = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
        # Alice searched at 9:00 and 9:20, then 40 minutes later; a staff member at 9:10.
        self.ids = {}
        for name, user, minutes in (("a1", alice, 0), ("a2", alice, 20), ("a3", alice, 60), ("s1", staff, 10)):
            search = Search.objects.create(user=user, filters={"lang": "en"}, matches=5)
            Search.objects.filter(pk=search.pk).update(created_at=start + timedelta(minutes=minutes))
            self.ids[name] = search.pk

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        self.searches = executor.loader.project_state(AFTER).apps.get_model("users", "SearchSnapshot")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_groups_each_users_searches_into_sittings_and_drops_the_user(self):
        stored = {row["id"]: row for row in self.searches.objects.values()}
        a1, a2, a3, s1 = (stored[self.ids[name]] for name in ("a1", "a2", "a3", "s1"))

        self.assertEqual([a1["sitting"], a2["sitting"]], [self.ids["a1"]] * 2)
        self.assertEqual(a3["sitting"], self.ids["a3"])
        self.assertEqual(s1["sitting"], self.ids["s1"])
        self.assertEqual([row["staff"] for row in (a1, a2, a3, s1)], [False, False, False, True])
        self.assertNotIn("user_id", a1)
