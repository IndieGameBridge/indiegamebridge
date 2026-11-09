"""Tests for the streamer search endpoint's numbered pages (GET /streamers/?p=N)."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch


class StreamerSearchPagesTests(TestCase):
    def setUp(self):
        # The throttles count in the cache, which outlives a test.
        cache.clear()
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()
        # Three streamers the default search finds, the highest peak first.
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

    def _get(self, page):
        # Two a page, so the three streamers make two pages.
        with mock.patch("apps.api.views.SEARCH_PAGE_SIZE", 2):
            response = self.client.get("/streamers/", {"lang": "en", "p": page})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _logins(self, data):
        return [row["login"] for row in data["results"]]

    def test_a_page_holds_its_own_rows(self):
        data = self._get("2")

        self.assertEqual((data["total"], data["page"], data["pages"], data["page_size"]), (3, 2, 2, 2))
        self.assertEqual(self._logins(data), ["streamer3"])

    def test_a_page_past_the_end_reads_as_the_last(self):
        data = self._get("9")

        self.assertEqual(data["page"], 2)
        self.assertEqual(self._logins(data), ["streamer3"])

    def test_a_page_that_isnt_a_number_reads_as_the_first(self):
        data = self._get("abc")

        self.assertEqual(data["page"], 1)
        self.assertEqual(self._logins(data), ["streamer1", "streamer2"])
