"""Tests for one list and its entries (GET /api/lists/<id>/)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import PAGE_SIZE, StreamerSearch
from apps.userlists.models import StreamerInList, UserListOfStreamers
from apps.userlists.views import ListDetailView

User = get_user_model()


class ListDetailTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()

        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")
        self.list = self._make_list(self.user, search={"lang": "en", "peakmax": "any"})

    def _make_list(self, owner, search=None):
        return UserListOfStreamers.objects.create(
            owner=owner,
            title="small streamers",
            search_filters=StreamerSearch(search).explicit_filters() if search else {},
        )

    def _make_streamer(self, host_user_id, login, languages=("en",)):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )
        for language in languages:
            StreamerSearchStats.objects.create(
                streamer_profile=profile,
                language=language,
                peak_viewers=100,
                avg_viewers=50,
                total_duration_seconds=36000,
                streams_count=8,
                genre_ids=[],
                host_login=login,
                host_display_name=login.title(),
            )
        return profile

    def _add(self, profile, list_of_streamers=None, description=""):
        return StreamerInList.objects.create(
            list_of_streamers=list_of_streamers or self.list,
            streamer_profile=profile,
            description=description,
        )

    def _get(self, list_id=None, user=None, page=None):
        list_id = list_id or self.list.id
        request = self.factory.get(f"/api/lists/{list_id}/", {"p": page} if page else {})
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListDetailView.as_view()(request, list_id=list_id)

    def test_returns_the_entries_in_saved_order_with_their_stats(self):
        for index, login in enumerate(("top", "middle", "small"), start=1):
            self._add(self._make_streamer(index, login), description=f"note on {login}")

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["streamers_count"], 3)
        entries = response.data["entries"]
        self.assertEqual(
            [entry["streamer"]["login"] for entry in entries], ["top", "middle", "small"],
        )
        self.assertEqual(entries[0]["description"], "note on top")
        self.assertEqual(
            entries[0]["streamer"]["stats"],
            {"peak_viewers": 100, "avg_viewers": 50, "streams_count": 8, "hours_streamed": 10, "genres": []},
        )

    def test_stats_come_from_the_lists_language(self):
        # The list was searched in English. A streamer who now only streams in
        # French stays in it, just without numbers to show.
        self._add(self._make_streamer(1, "bilingual", languages=("en", "fr")))
        self._add(self._make_streamer(2, "moved_on", languages=("fr",)))

        entries = self._get().data["entries"]

        self.assertIsNotNone(entries[0]["streamer"]["stats"])
        self.assertIsNone(entries[1]["streamer"]["stats"])

    def test_an_opted_out_streamer_comes_back_anonymized_with_its_note(self):
        streamer = self._make_streamer(1, "gone")
        self._add(streamer, description="replied 3 Sep, wants a key")
        streamer.delete()

        (entry,) = self._get().data["entries"]

        self.assertIsNone(entry["streamer"])
        self.assertEqual(entry["description"], "replied 3 Sep, wants a key")

    def test_pages_through_the_entries(self):
        for index in range(PAGE_SIZE + 1):
            self._add(self._make_streamer(index + 1, f"streamer{index}", languages=()))

        first = self._get().data
        second = self._get(page=2).data

        self.assertEqual(len(first["entries"]), PAGE_SIZE)
        self.assertEqual(
            [entry["streamer"]["login"] for entry in second["entries"]], [f"streamer{PAGE_SIZE}"],
        )
        self.assertEqual(second["streamers_count"], PAGE_SIZE + 1)

    def test_describes_the_search_it_was_saved_from(self):
        search = self._get().data["search"]

        self.assertIn({"label": "Language", "value": "English"}, search)
        # No max was set, so the summary shows an open-ended range.
        self.assertIn({"label": "Max Viewers", "value": "5+"}, search)

    def test_a_list_without_a_recorded_search_has_no_stats_or_summary(self):
        legacy = self._make_list(self.user)
        self._add(self._make_streamer(1, "solo"), list_of_streamers=legacy)

        data = self._get(list_id=legacy.id).data

        self.assertEqual(data["search"], [])
        self.assertIsNone(data["entries"][0]["streamer"]["stats"])

    def test_another_users_list_is_not_found(self):
        theirs = self._make_list(self.other, search={"lang": "en"})

        # Same answer as a list that doesn't exist, so ids can't be probed.
        self.assertEqual(self._get(list_id=theirs.id).status_code, 404)
        self.assertEqual(self._get(list_id=theirs.id + 1000).status_code, 404)

    def test_requires_authentication(self):
        self.assertIn(self._get(user=False).status_code, (401, 403))
