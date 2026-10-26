"""Tests for adding streamers to a list (POST /api/lists/<id>/entries/): one, or a whole search."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle

from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch
from apps.userlists.models import StreamerInList, UserListOfStreamers
from apps.userlists.views import ListEntriesView

User = get_user_model()


class ListEntriesTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()

        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")
        self.list = UserListOfStreamers.objects.create(owner=self.user, title="to contact")

    def _make_streamer(self, host_user_id, login, peak=100):
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
            avg_viewers=50,
            total_duration_seconds=36000,
            streams_count=8,
            genre_ids=[],
            host_login=login,
            host_display_name=login.title(),
        )
        return profile

    def _add(self, profile):
        return StreamerInList.objects.create(list_of_streamers=self.list, streamer_profile=profile)

    def _post(self, payload, list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.post(f"/api/lists/{list_id}/entries/", payload, format="json")
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListEntriesView.as_view()(request, list_id=list_id)

    def _logins(self):
        return list(self.list.entries.values_list("streamer_profile__host_login", flat=True))

    def test_adds_one_streamer_to_the_end(self):
        self._add(self._make_streamer(1, "first"))
        streamer = self._make_streamer(2, "second")

        response = self._post({"profile_id": streamer.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"added": 1, "already_in_list": 0, "streamers_count": 2},
        )
        self.assertEqual(self._logins(), ["first", "second"])

    def test_adding_a_streamer_already_in_the_list_changes_nothing(self):
        streamer = self._make_streamer(1, "solo")
        self._add(streamer)

        response = self._post({"profile_id": streamer.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"added": 0, "already_in_list": 1, "streamers_count": 1},
        )
        self.assertEqual(self._logins(), ["solo"])

    def test_rejects_a_streamer_that_is_not_an_id(self):
        for bad_id in ("1", True, None, [1]):
            with self.subTest(profile_id=bad_id):
                self.assertEqual(self._post({"profile_id": bad_id}).status_code, 400)

        self.assertFalse(self.list.entries.exists())

    def test_rejects_a_streamer_who_is_gone(self):
        streamer = self._make_streamer(1, "gone")
        streamer_id = streamer.id
        streamer.delete()

        response = self._post({"profile_id": streamer_id})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.list.entries.exists())

    def test_adds_a_searchs_results_after_the_entries_skipping_the_ones_already_in(self):
        self._add(self._make_streamer(1, "added_by_hand", peak=20))
        middle = self._make_streamer(2, "middle", peak=100)
        self._add(middle)
        self._make_streamer(3, "top", peak=150)
        self._make_streamer(4, "small", peak=50)

        response = self._post({"search": "lang=en"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"added": 2, "already_in_list": 2, "streamers_count": 4},
        )
        # The new ones follow the existing entries, in the search's own order.
        self.assertEqual(self._logins(), ["added_by_hand", "middle", "top", "small"])

    def test_applies_the_searchs_filters(self):
        self._make_streamer(1, "big", peak=150)
        self._make_streamer(2, "tiny", peak=20)

        response = self._post({"search": "lang=en&peakmin=100"})

        self.assertEqual(response.data["added"], 1)
        self.assertEqual(self._logins(), ["big"])

    def test_rejects_a_search_that_is_not_a_query_string(self):
        self._make_streamer(1, "top")

        for bad_search in (5, None, ["lang=en"], {"lang": "en"}):
            with self.subTest(search=bad_search):
                self.assertEqual(self._post({"search": bad_search}).status_code, 400)

        self.assertFalse(self.list.entries.exists())

    def test_needs_either_a_streamer_or_a_search(self):
        streamer = self._make_streamer(1, "top")

        for payload in ({}, {"profile_id": streamer.id, "search": "lang=en"}):
            with self.subTest(payload=payload):
                self.assertEqual(self._post(payload).status_code, 400)

        self.assertFalse(self.list.entries.exists())

    def test_refuses_an_add_that_would_overflow_the_list(self):
        self._add(self._make_streamer(1, "first"))
        self._make_streamer(2, "second")
        self._make_streamer(3, "third")

        with mock.patch("apps.userlists.views.list_entries.MAX_STREAMERS_PER_LIST", 2):
            response = self._post({"search": "lang=en"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)
        # Refused whole, not cut down to what would fit.
        self.assertEqual(self._logins(), ["first"])

    def test_a_streamer_already_in_a_full_list_is_not_an_overflow(self):
        streamer = self._make_streamer(1, "solo")
        self._add(streamer)

        with mock.patch("apps.userlists.views.list_entries.MAX_STREAMERS_PER_LIST", 1):
            response = self._post({"profile_id": streamer.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["added"], 0)

    def test_anonymized_entries_count_towards_the_size(self):
        gone = self._make_streamer(1, "gone")
        self._add(gone)
        gone.delete()
        streamer = self._make_streamer(2, "new")

        with mock.patch("apps.userlists.views.list_entries.MAX_STREAMERS_PER_LIST", 1):
            response = self._post({"profile_id": streamer.id})

        self.assertEqual(response.status_code, 400)

    def test_another_users_list_is_not_found(self):
        theirs = UserListOfStreamers.objects.create(owner=self.other, title="theirs")
        streamer = self._make_streamer(1, "top")

        response = self._post({"profile_id": streamer.id}, list_id=theirs.id)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(StreamerInList.objects.exists())

    def test_requires_authentication(self):
        streamer = self._make_streamer(1, "top")

        response = self._post({"profile_id": streamer.id}, user=False)

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(StreamerInList.objects.exists())

    def test_only_adding_a_search_spends_the_write_budget(self):
        # Result rows add one streamer per click; if those shared the tight
        # write rate, working through a page of results would lock the user out.
        streamers = [self._make_streamer(index, f"streamer{index}") for index in range(1, 4)]

        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"userlists_write": "1/hour"}):
            for streamer in streamers:
                self.assertEqual(self._post({"profile_id": streamer.id}).status_code, 200)
            self.assertEqual(self._post({"search": "lang=en"}).status_code, 200)
            self.assertEqual(self._post({"search": "lang=en"}).status_code, 429)
