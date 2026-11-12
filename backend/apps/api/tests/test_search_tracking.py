"""Tests for recording streamer searches (GET /streamers/): which searches get a SearchSnapshot."""

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import AccessToken

from apps.api.views import StreamerSearchView
from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch
from apps.users.models import AccountSettings, SearchSnapshot
from apps.users.models.search_snapshot import REPEAT_WINDOW

User = get_user_model()


class SearchTrackingTests(TestCase):
    def setUp(self):
        # The throttles count in the cache, which outlives a test.
        cache.clear()
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        # Three streamers the default search finds.
        for number, peak in enumerate((150, 120, 90), start=1):
            profile = StreamerProfile.objects.create(
                host=StreamerProfile.Host.TWITCH,
                host_user_id=number,
                host_login=f"streamer{number}",
                host_display_name=f"Streamer{number}",
            )
            StreamerSearchStats.objects.create(
                streamer_profile=profile,
                language="en",
                peak_viewers=peak,
                avg_viewers=50,
                total_duration_seconds=36000,
                streams_count=8,
                genre_ids=[],
                host_login=profile.host_login,
                host_display_name=profile.host_display_name,
            )

    def _search(self, query="", user=None):
        request = self.factory.get(f"/streamers/?{query}")
        if user is not False:
            force_authenticate(request, user=user or self.user)
        # Two a page, so the three streamers make two pages.
        with mock.patch("apps.api.views.SEARCH_PAGE_SIZE", 2):
            response = StreamerSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response

    def _search_with_cookie(self, token):
        """The way the search page calls: with the user's access cookie forwarded."""
        request = self.factory.get("/streamers/", HTTP_COOKIE=f"{settings.JWT_ACCESS_COOKIE_NAME}={token}")
        response = StreamerSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response

    def test_records_a_search_with_every_filter_and_its_matches(self):
        self._search("peak=any&genres=any")

        snapshot = SearchSnapshot.objects.get()
        self.assertEqual(snapshot.user, self.user)
        self.assertEqual(snapshot.filters, StreamerSearch({"peak": "any"}).explicit_filters())
        self.assertEqual((snapshot.filters["peak"], snapshot.filters["avgmin"]), ("any", 5))
        self.assertEqual(snapshot.matches, 3)

    def test_counts_the_matches_past_the_cap(self):
        with mock.patch("apps.streams.search.MAX_RESULTS", 2):
            response = self._search()

        self.assertEqual(response.data["total"], 2)
        self.assertEqual(SearchSnapshot.objects.get().matches, 3)

    def test_paging_on_records_nothing_new(self):
        self._search()
        self._search("p=2")

        self.assertEqual(SearchSnapshot.objects.count(), 1)

    def test_a_later_page_alone_records_nothing(self):
        self._search("p=2")

        self.assertFalse(SearchSnapshot.objects.exists())

    def test_the_same_search_again_soon_counts_once(self):
        self._search("lang=en")
        # The same filters, spelled out differently.
        self._search("lang=en&peak=51-200&p=1")

        self.assertEqual(SearchSnapshot.objects.count(), 1)

    def test_the_same_search_after_the_window_counts_again(self):
        self._search()
        first = SearchSnapshot.objects.get()
        SearchSnapshot.objects.update(created_at=first.created_at - REPEAT_WINDOW - timedelta(minutes=1))

        self._search()

        self.assertEqual(SearchSnapshot.objects.count(), 2)

    def test_another_search_counts(self):
        self._search()
        self._search("peak=21-50")
        self._search("peak=any")

        self.assertEqual(
            [snapshot.filters["peak"] for snapshot in SearchSnapshot.objects.order_by("created_at")],
            ["51-200", "21-50", "any"],
        )
        self.assertEqual([snapshot.matches for snapshot in SearchSnapshot.objects.order_by("created_at")], [3, 0, 3])

    def test_another_users_same_search_is_theirs(self):
        self._search()
        self._search(user=User.objects.create_user(username="other"))

        self.assertEqual(SearchSnapshot.objects.count(), 2)

    def test_records_nothing_for_a_user_who_turned_tracking_off(self):
        AccountSettings.objects.create(user=self.user, allow_tracking=False)

        self._search()

        self.assertFalse(SearchSnapshot.objects.exists())

    def test_records_the_user_whose_cookie_the_page_forwards(self):
        self._search_with_cookie(AccessToken.for_user(self.user))

        self.assertEqual(SearchSnapshot.objects.get().user, self.user)

    def test_a_cookie_that_doesnt_validate_reads_as_logged_out(self):
        response = self._search_with_cookie("not-a-token")

        self.assertEqual(response.data["total"], 3)
        self.assertFalse(SearchSnapshot.objects.exists())

    def test_records_nothing_for_a_logged_out_request(self):
        self._search(user=False)

        self.assertFalse(SearchSnapshot.objects.exists())

    def test_the_results_still_come_when_recording_fails(self):
        with mock.patch.object(SearchSnapshot.objects, "create", side_effect=RuntimeError("db down")):
            with self.assertLogs("apps.api", level="ERROR"):
                response = self._search()

        self.assertEqual([row["login"] for row in response.data["results"]], ["streamer1", "streamer2"])
