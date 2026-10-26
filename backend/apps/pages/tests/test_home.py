"""Tests for the home page's headline counts, read from the search table."""

from django.test import TestCase

from apps.pages.cached_pages.home import HomePageBuilder
from apps.streams.models import StreamerProfile, StreamerSearchStats


class SearchWindowCountsTests(TestCase):
    def _streamer(self, host_user_id):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"login{host_user_id}",
            host_display_name=f"Display{host_user_id}",
        )

    def _search_row(self, profile, language, streams_count):
        return StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language=language,
            peak_viewers=10,
            avg_viewers=5,
            total_duration_seconds=3600,
            streams_count=streams_count,
            host_login=profile.host_login,
            host_display_name=profile.host_display_name,
        )

    def test_counts_each_streamer_once_and_every_stream(self):
        bilingual = self._streamer(1)
        self._search_row(bilingual, "en", 3)
        self._search_row(bilingual, "fr", 2)
        self._search_row(self._streamer(2), "de", 4)

        self.assertEqual(HomePageBuilder._search_window_counts(), (2, 9))

    def test_an_empty_search_table_counts_zero(self):
        self.assertEqual(HomePageBuilder._search_window_counts(), (0, 0))
