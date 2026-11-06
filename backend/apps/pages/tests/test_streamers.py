"""Tests for the Streamers page's payload: the logged-out page and its demo."""

from unittest import mock

from django.test import TestCase

from apps.pages.cached_pages.streamers import StreamersPageBuilder
from apps.streams.models import StreamerProfile, StreamerSearchStats


class StreamersPageTests(TestCase):
    def _streamer(self, host_user_id, peak_viewers):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"login{host_user_id}",
            host_display_name=f"Display{host_user_id}",
        )
        return StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language="en",
            peak_viewers=peak_viewers,
            avg_viewers=50,
            total_duration_seconds=36000,
            streams_count=8,
            host_login=profile.host_login,
            host_display_name=profile.host_display_name,
        )

    def test_the_demo_shows_the_default_search_highest_peak_first(self):
        self._streamer(1, 100)
        self._streamer(2, 150)
        self._streamer(3, 5)  # Below the default size group.

        content = StreamersPageBuilder().build_content()

        self.assertEqual([row["login"] for row in content["search_results"]], ["login2", "login1"])
        self.assertEqual(content["search_total"], 2)

    @mock.patch("apps.pages.cached_pages.streamers.DEMO_ROWS", 1)
    def test_the_demo_stops_at_its_rows_but_counts_them_all(self):
        self._streamer(1, 100)
        self._streamer(2, 150)

        content = StreamersPageBuilder().build_content()

        self.assertEqual([row["login"] for row in content["search_results"]], ["login2"])
        self.assertEqual(content["search_total"], 2)

    def test_the_public_page_says_the_search_needs_a_login(self):
        page = StreamersPageBuilder().build_content()["public_page"]

        self.assertIn("You need to log in", page["login_note"])

    def test_only_the_login_items_skip_a_logged_in_reader(self):
        page = StreamersPageBuilder().build_content()["public_page"]

        marked = [
            one.get("title") or one.get("question")
            for one in page["how_to"]["steps"] + page["faq"]["items"]
            if one.get("logged_out_only")
        ]
        self.assertEqual(marked, ["Log in with Twitch.", "Do I need an account to search Twitch streamers here?"])

    def test_the_public_page_counts_the_streamers_and_names_the_languages(self):
        self._streamer(1, 100)

        about = " ".join(StreamersPageBuilder().build_content()["public_page"]["about"]["paragraphs"])

        self.assertIn("It covers 1 streamers", about)
        self.assertIn("English, French", about)
