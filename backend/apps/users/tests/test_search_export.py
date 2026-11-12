"""Tests for the admin's search snapshots: the list, and exporting the newest as a CSV file."""

import csv
import io
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.streams.models import GameGenre
from apps.streams.search import StreamerSearch
from apps.users.models import SearchSnapshot

User = get_user_model()

HEADER = [
    "user", "searched_at_utc", "search_number", "minutes_since_previous_search", "matches",
    "language", "max_viewers", "avg_viewers_min", "avg_viewers_max", "streams_min", "streams_max",
    "hours_min", "hours_max", "genres", "staff",
]


class SearchExportTests(TestCase):
    def setUp(self):
        for host_genre_id, name in ((15, "Strategy"), (32, "Indie")):
            GameGenre.objects.create(host_genre_id=host_genre_id, host_name=name, host_url="", slug=name.lower())
        # The form's genre options come from the rows above.
        StreamerSearch.get_filters_config.cache_clear()
        self.admin = User.objects.create_superuser(username="admin", password="unused")
        self.client.force_login(self.admin)
        self.alice = User.objects.create_user(username="alice")

    def _search(self, user, when, matches=12, **filters):
        snapshot = SearchSnapshot.objects.create(
            user=user, filters=StreamerSearch(filters).explicit_filters(), matches=matches,
        )
        SearchSnapshot.objects.filter(pk=snapshot.pk).update(created_at=when)

    def _export(self):
        response = self.client.get(reverse("admin:users_searchsnapshot_export"))
        return response, list(csv.reader(io.StringIO(response.content.decode())))

    def test_numbers_each_users_searches_and_the_minutes_between_them(self):
        self._search(self.alice, datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
        self._search(self.alice, datetime(2026, 10, 1, 9, 12, 40, tzinfo=UTC), matches=7400, lang="de", peak="any")

        _, (header, newest, first) = self._export()

        self.assertEqual(header, HEADER)
        self.assertEqual(newest, [
            str(self.alice.pk), "2026-10-01 09:12", "2", "12", "7400",
            "de", "any", "5", "200", "8", "any", "8", "any", "any", "no",
        ])
        self.assertEqual(first[1:7], ["2026-10-01 09:00", "1", "", "12", "en", "51-200"])

    def test_names_the_genres_picked(self):
        self._search(self.alice, datetime(2026, 10, 1, tzinfo=UTC), genres="15", genres3="32")

        _, (_, row) = self._export()

        self.assertEqual(row[HEADER.index("genres")], "Strategy + Indie")

    def test_marks_staff_searches_and_leaves_out_names(self):
        self._search(self.admin, datetime(2026, 10, 1, tzinfo=UTC))

        response, (_, row) = self._export()

        self.assertEqual(row[HEADER.index("staff")], "yes")
        self.assertNotContains(response, "admin")

    def test_the_list_shows_what_narrowed_each_search_and_offers_the_export(self):
        self._search(self.alice, datetime(2026, 10, 1, tzinfo=UTC), genres="15", hoursmin="any")

        response = self.client.get(reverse("admin:users_searchsnapshot_changelist"))

        self.assertContains(
            response, "Max Viewers: 51-200; Avg Viewers: 5–200; Streams: 8+; Game Genre #1: Strategy; Language: English",
        )
        self.assertContains(response, f'action="{reverse("admin:users_searchsnapshot_export")}"')
