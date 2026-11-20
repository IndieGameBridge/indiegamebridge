"""Tests for the current user endpoint's link to the user's own streamer profile."""

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.streams.models import StreamerProfile
from apps.users.views.current_user import CurrentUserView

User = get_user_model()


class CurrentUserStreamerProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dev")

    def _streamer_login(self):
        request = APIRequestFactory().get("/auth/currentuser/")
        force_authenticate(request, user=self.user)
        response = CurrentUserView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response.data["streamer_login"]

    def test_names_the_users_own_streamer_profile(self):
        SocialAccount.objects.create(user=self.user, provider="twitch", uid="4242")
        # Found by Twitch ID, so a login changed since the user signed up still leads there.
        StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH, host_user_id=4242, host_login="new_name", host_display_name="New_Name",
        )

        self.assertEqual(self._streamer_login(), "new_name")

    def test_names_none_for_a_user_we_have_no_streams_from(self):
        SocialAccount.objects.create(user=self.user, provider="twitch", uid="4242")

        self.assertIsNone(self._streamer_login())

    def test_names_none_without_a_twitch_account(self):
        self.assertIsNone(self._streamer_login())
