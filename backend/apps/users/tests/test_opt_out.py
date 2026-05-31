"""Tests for opt-out data removal (perform_opt_out).

perform_opt_out records the exclusion and erases the data collected for the
user's Twitch ID: the StreamerProfile plus its cascaded streams and cached
profile payload. The standalone OptOutView and the settings-page
StreamExclusionView both delegate to this helper.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.streams.models import Stream, StreamerProfile, StreamerProfileCache
from apps.users.adapters import OptOutSocialAccountAdapter
from apps.users.models import TwitchExclusion
from apps.users.views.opt_out import perform_opt_out

User = get_user_model()

TWITCH_ID = 123456789
OTHER_TWITCH_ID = 987654321


class PerformOptOutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="streamer")
        SocialAccount.objects.create(user=self.user, provider="twitch", uid=str(TWITCH_ID))

    def _make_streamer_with_data(self, host_user_id, login="streamer"):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )
        Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=1,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=1),
            snapshots=[],
        )
        StreamerProfileCache.objects.create(streamer_profile=profile, content={})
        return profile

    def test_records_exclusion_and_deletes_streamer_data(self):
        self._make_streamer_with_data(TWITCH_ID)

        result = perform_opt_out(self.user)

        self.assertTrue(result)  # a new exclusion was created
        self.assertTrue(TwitchExclusion.objects.filter(twitch_id=TWITCH_ID).exists())
        self.assertFalse(StreamerProfile.objects.filter(host_user_id=TWITCH_ID).exists())
        # Streams and the cached payload cascade-delete with the profile.
        self.assertEqual(Stream.objects.count(), 0)
        self.assertEqual(StreamerProfileCache.objects.count(), 0)

    def test_leaves_other_streamers_untouched(self):
        self._make_streamer_with_data(TWITCH_ID)
        other = self._make_streamer_with_data(OTHER_TWITCH_ID, login="other")

        perform_opt_out(self.user)

        self.assertTrue(StreamerProfile.objects.filter(pk=other.pk).exists())
        self.assertEqual(Stream.objects.filter(streamer_profile=other).count(), 1)
        self.assertEqual(StreamerProfileCache.objects.filter(streamer_profile=other).count(), 1)

    def test_idempotent_when_already_excluded(self):
        self._make_streamer_with_data(TWITCH_ID)
        perform_opt_out(self.user)

        result = perform_opt_out(self.user)

        self.assertFalse(result)  # already opted out, no new row
        self.assertEqual(TwitchExclusion.objects.filter(twitch_id=TWITCH_ID).count(), 1)

    def test_without_twitch_account_is_noop(self):
        user = User.objects.create_user(username="no_twitch")

        result = perform_opt_out(user)

        self.assertIsNone(result)
        self.assertEqual(TwitchExclusion.objects.count(), 0)


class OptOutSocialAdapterTests(TestCase):
    """The opt-out OAuth flow must record the opt-out and short-circuit before
    allauth ever creates an account."""

    def _sociallogin(self, twitch_id, next_url):
        sociallogin = mock.Mock()
        sociallogin.state = {"next": next_url}
        sociallogin.account = mock.Mock()
        sociallogin.account.uid = str(twitch_id)
        return sociallogin

    def _make_streamer_with_data(self, host_user_id):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login="streamer",
            host_display_name="Streamer",
        )
        Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=1,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=1),
            snapshots=[],
        )
        return profile

    def test_optout_flow_opts_out_and_creates_no_account(self):
        self._make_streamer_with_data(TWITCH_ID)
        adapter = OptOutSocialAccountAdapter()
        sociallogin = self._sociallogin(
            TWITCH_ID,
            "/auth/finalize-login/?action=optout&next=/optout?status=done",
        )

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(mock.Mock(), sociallogin)

        # Short-circuits with a redirect to the opt-out success page.
        response = ctx.exception.response
        self.assertEqual(response.status_code, 302)
        self.assertIn("/optout", response.url)
        self.assertIn("new=yes", response.url)
        # Opt-out recorded and streamer data erased.
        self.assertTrue(TwitchExclusion.objects.filter(twitch_id=TWITCH_ID).exists())
        self.assertFalse(StreamerProfile.objects.filter(host_user_id=TWITCH_ID).exists())
        # No account was created.
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_normal_login_is_untouched(self):
        adapter = OptOutSocialAccountAdapter()
        sociallogin = self._sociallogin(TWITCH_ID, "/auth/finalize-login/?next=/")

        # No action=optout in next -> returns without raising or opting out.
        result = adapter.pre_social_login(mock.Mock(), sociallogin)

        self.assertIsNone(result)
        self.assertEqual(TwitchExclusion.objects.count(), 0)
