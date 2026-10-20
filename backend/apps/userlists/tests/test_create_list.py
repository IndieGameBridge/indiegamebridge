"""Tests for creating a list (POST /api/lists/).

The endpoint takes a search's query string rather than its result ids, so these
build StreamerSearchStats rows directly (the rebuild itself is covered in
apps.streams.tests.test_search) and check that the saved list matches what the
same search would have returned.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch
from apps.userlists.models import (
    StreamerInList,
    UserLabelForListOfStreamers,
    UserListOfStreamers,
)
from apps.userlists.views.lists import MAX_LISTS_PER_USER, ListsView

User = get_user_model()


class CreateListTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()

        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")

    def _make_streamer(self, host_user_id, login, peak=100, avg=50):
        """A streamer that passes the search form's default filters."""
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )
        StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language="en",
            peak_viewers=peak,
            avg_viewers=avg,
            total_duration_seconds=36000,
            streams_count=8,
            genre_ids=[],
            host_login=login,
            host_display_name=login.title(),
        )
        return profile

    def _make_label(self, owner=None, title="shooters", color="#0072B2"):
        return UserLabelForListOfStreamers.objects.create(
            owner=owner or self.user, title=title, color=color,
        )

    def _post(self, user=None, **payload):
        payload.setdefault("title", "small streamers")
        payload.setdefault("search", "lang=en")
        request = self.factory.post("/api/lists/", payload, format="json")
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListsView.as_view()(request)

    def test_creates_a_list_from_the_search(self):
        self._make_streamer(1, "top", peak=150)
        self._make_streamer(2, "middle", peak=100)
        self._make_streamer(3, "small", peak=50)

        response = self._post(description="for the shooter pitch")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["streamers_count"], 3)

        saved = UserListOfStreamers.objects.get(id=response.data["id"])
        self.assertEqual(saved.owner, self.user)
        self.assertEqual(saved.description, "for the shooter pitch")
        # Rows are written in result order, so the list reads back ranked by peak.
        self.assertEqual(
            list(saved.entries.values_list("streamer_profile__host_login", flat=True)),
            ["top", "middle", "small"],
        )

    def test_applies_the_searchs_filters(self):
        self._make_streamer(1, "big", peak=150)
        self._make_streamer(2, "tiny", peak=20)

        response = self._post(search="lang=en&peakmin=100")

        self.assertEqual(response.status_code, 201)
        saved = UserListOfStreamers.objects.get(id=response.data["id"])
        self.assertEqual(
            list(saved.entries.values_list("streamer_profile__host_login", flat=True)),
            ["big"],
        )

    def test_stores_the_search_it_was_saved_from(self):
        response = self._post(search="lang=en&peakmin=100&peakmax=any")

        saved = UserListOfStreamers.objects.get(id=response.data["id"])
        # Spelled out, "any" included, so a refresh can re-run it as it was.
        self.assertEqual(saved.search_filters["peakmin"], 100)
        self.assertEqual(saved.search_filters["peakmax"], "any")
        self.assertEqual(saved.search_filters["lang"], "en")

    def test_a_search_matching_nothing_still_saves_an_empty_list(self):
        response = self._post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["streamers_count"], 0)
        self.assertTrue(UserListOfStreamers.objects.exists())

    def test_requires_a_title(self):
        for blank in ("", "   "):
            with self.subTest(title=blank):
                response = self._post(title=blank)

                self.assertEqual(response.status_code, 400)
        self.assertFalse(UserListOfStreamers.objects.exists())

    def test_rejects_over_long_text(self):
        self.assertEqual(self._post(title="t" * 33).status_code, 400)
        self.assertEqual(self._post(description="d" * 513).status_code, 400)

        self.assertFalse(UserListOfStreamers.objects.exists())

    def test_attaches_the_owners_labels(self):
        shooters = self._make_label(title="shooters")
        priority = self._make_label(title="priority", color="#D55E00")

        response = self._post(labels=[shooters.id, priority.id])

        self.assertEqual(response.status_code, 201)
        saved = UserListOfStreamers.objects.get(id=response.data["id"])
        self.assertCountEqual(
            saved.labels.values_list("title", flat=True), ["shooters", "priority"],
        )

    def test_another_users_label_is_rejected_like_a_missing_one(self):
        theirs = self._make_label(owner=self.other)

        not_mine = self._post(labels=[theirs.id])
        missing = self._post(labels=[theirs.id + 1000])

        self.assertEqual(not_mine.status_code, 400)
        # Identical answers, so this can't be used to probe for others' label ids.
        self.assertEqual(not_mine.data, missing.data)
        self.assertFalse(UserListOfStreamers.objects.exists())

    def test_rejects_labels_that_are_not_a_list_of_ids(self):
        for bad_labels in ("shooters", [True], ["1"], {"id": 1}):
            with self.subTest(labels=bad_labels):
                response = self._post(labels=bad_labels)

                self.assertEqual(response.status_code, 400)

    def test_enforces_the_per_user_cap(self):
        for index in range(MAX_LISTS_PER_USER):
            UserListOfStreamers.objects.create(owner=self.user, title=f"list {index}")

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserListOfStreamers.objects.count(), MAX_LISTS_PER_USER)

    def test_the_cap_is_per_user(self):
        for index in range(MAX_LISTS_PER_USER):
            UserListOfStreamers.objects.create(owner=self.other, title=f"list {index}")

        response = self._post()

        self.assertEqual(response.status_code, 201)

    def test_requires_authentication(self):
        response = self._post(user=False)

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(UserListOfStreamers.objects.exists())

    def test_a_failed_entry_write_leaves_no_partial_list(self):
        # The list row, its labels and its entries go in one transaction, so a
        # failure partway through must not leave a titled but empty list behind.
        self._make_streamer(1, "top")

        with mock.patch(
            "apps.userlists.views.lists.StreamerInList.objects.bulk_create",
            side_effect=DatabaseError("write failed"),
        ):
            with self.assertRaises(DatabaseError):
                self._post()

        self.assertFalse(UserListOfStreamers.objects.exists())
        self.assertFalse(StreamerInList.objects.exists())
