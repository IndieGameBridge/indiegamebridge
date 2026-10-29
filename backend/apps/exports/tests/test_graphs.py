"""Tests for the admin's Exports > Graphs page."""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.exports.graphs import export_graphs
from apps.exports.models import Export
from apps.userlists.models import UserListOfStreamers

User = get_user_model()

# Thursday noon, UTC.
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=dt_timezone.utc)


class ExportGraphsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")
        self.list = UserListOfStreamers.objects.create(owner=self.user, title="Cozy")

    def _export(self, user, days_ago, hours=0, list_of_streamers=None, search_filters=None):
        export = Export.objects.create(
            user=user,
            source=Export.Source.LIST if list_of_streamers else Export.Source.SEARCH,
            list_of_streamers=list_of_streamers,
            search_filters=search_filters or {},
            file_format=Export.FileFormat.CSV,
            rows=10,
        )
        # created_at is set on create; move it to when the test says.
        Export.objects.filter(pk=export.pk).update(created_at=NOW - timedelta(days=days_ago, hours=hours))

    def _days(self):
        return export_graphs(14, now=NOW)["hover_sources"][0].rows

    def test_the_same_export_on_a_later_day_counts_as_again(self):
        self._export(self.user, 2, list_of_streamers=self.list)
        self._export(self.user, 2, hours=1, list_of_streamers=self.list)  # the same day: not again
        self._export(self.other, 1, search_filters={"lang": "en"})
        self._export(self.user, 0, list_of_streamers=self.list)  # again
        self._export(self.other, 0, search_filters={"lang": "en"})  # again: the same search

        days = self._days()

        # Exports, again, first, users for Tue 27, Wed 28 and Thu 29 Oct.
        self.assertEqual(
            [day["values"] for day in days],
            [["2", "0", "2", "1 user"], ["1", "0", "1", "1 user"], ["2", "2", "0", "2 users"]],
        )

    def test_another_users_or_another_searchs_export_is_a_first(self):
        self._export(self.user, 1, search_filters={"lang": "en", "genre": ["rpg"]})
        self._export(self.other, 0, search_filters={"lang": "en", "genre": ["rpg"]})
        self._export(self.user, 0, search_filters={"lang": "de", "genre": ["rpg"]})

        self.assertEqual(self._days()[-1]["values"], ["2", "0", "2", "2 users"])

    def test_exports_of_a_deleted_list_match_nothing(self):
        self._export(self.user, 1, list_of_streamers=self.list)
        self._export(self.user, 0, list_of_streamers=self.list)
        self.list.delete()

        self.assertEqual(self._days()[-1]["values"], ["1", "0", "1", "1 user"])

    def test_tiles_count_who_came_back(self):
        self._export(self.user, 1, list_of_streamers=self.list)
        self._export(self.user, 0, list_of_streamers=self.list)
        self._export(self.other, 0, search_filters={"lang": "en"})

        tiles = {tile.label: tile.value for tile in export_graphs(14, now=NOW)["tiles"]}

        self.assertEqual(tiles, {"Exports": "3", "Exported again": "1", "Users who exported": "2", "Users who came back": "1"})

    def test_renders_for_an_admin(self):
        self._export(self.user, 0, list_of_streamers=self.list)
        Export.objects.update(created_at=timezone.now())
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

        response = self.client.get(reverse("admin:exports_export_graphs"))

        self.assertContains(response, 'class="viz-plot"', count=1)
        self.assertContains(response, "Exports per day")
