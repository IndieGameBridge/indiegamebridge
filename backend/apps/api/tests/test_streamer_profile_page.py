"""Tests for the streamer profile page's content (GET /pages/streamer_profile/?twitch_login=...)."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.api.views import CachedPageContentView
from apps.pages.models import CachedPage
from apps.streams.models import StreamerProfile


class StreamerProfilePageTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        CachedPage.objects.create(
            key="streamer_profile", content={"title": "Streamer: %streamer_display_name%"},
        )
        self.streamer = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=1,
            host_login="solo",
            host_display_name="Solo",
        )

    def _get(self, twitch_login):
        request = self.factory.get("/pages/streamer_profile/", {"twitch_login": twitch_login})
        return CachedPageContentView.as_view()(request, key="streamer_profile")

    def test_carries_the_profile_id_for_add_to_list(self):
        response = self._get("solo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Streamer: Solo")
        self.assertEqual(response.data["profile_id"], self.streamer.id)

    def test_an_unknown_streamer_has_no_profile_id(self):
        response = self._get("nobody")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["profile_id"])
