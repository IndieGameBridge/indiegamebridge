"""Tests for the Home page's streamer finder: the login read from what's typed or pasted, and
the lookup endpoint (GET /api/streamers/find/?q=...)."""

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.streams.models import StreamerProfile
from apps.streams.streamer_lookup import twitch_login_from


class TwitchLoginFromTests(SimpleTestCase):
    def test_reads_the_login_from_a_login_a_mention_or_a_channel_link(self):
        for text in (
            "shroud",
            " Shroud ",
            "@shroud",
            "twitch.tv/shroud",
            "www.twitch.tv/shroud",
            "https://www.twitch.tv/shroud",
            "http://m.twitch.tv/Shroud/videos?filter=archives",
            "https://twitch.tv/shroud#chat",
        ):
            with self.subTest(text=text):
                self.assertEqual(twitch_login_from(text), "shroud")

    def test_finds_no_login_in_anything_else(self):
        for text in (
            "",
            "   ",
            "@",
            "twitch.tv/",
            "two words",
            "https://www.youtube.com/@shroud",
            "https://clips.twitch.tv/SomeClip",
            # Twitch logins stop at 25 characters.
            "x" * 26,
            "shroud" + " " * 300 + "x",
        ):
            with self.subTest(text=text):
                self.assertIsNone(twitch_login_from(text))


class StreamerLookupViewTests(TestCase):
    def setUp(self):
        # The throttles count in the cache, which outlives a test.
        cache.clear()
        StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH, host_user_id=1, host_login="shroud", host_display_name="Shroud",
        )

    def _find(self, text):
        response = self.client.get(reverse("streamer-lookup"), {"q": text})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_finds_a_streamer_by_a_pasted_channel_link(self):
        self.assertEqual(
            self._find("https://www.twitch.tv/Shroud/videos"),
            {"valid": True, "profile": {"login": "shroud", "display_name": "Shroud"}},
        )

    def test_says_when_no_streamer_has_the_login(self):
        self.assertEqual(self._find("nobody_here"), {"valid": True, "profile": None})

    def test_says_when_the_text_holds_no_login(self):
        self.assertEqual(self._find("https://www.youtube.com/@shroud"), {"valid": False, "profile": None})

    def test_takes_no_notice_of_a_bad_access_token(self):
        # It acts for nobody, so a stale or forged token can't turn it into a 401.
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = "not-a-token"

        self.assertEqual(self._find("shroud")["profile"]["login"], "shroud")
