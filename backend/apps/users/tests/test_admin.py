"""Tests for the users-admin changelist annotations (streams opt-out column)."""

from allauth.socialaccount.models import SocialAccount
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.users.admin import CustomUserAdmin
from apps.users.models import TwitchExclusion

User = get_user_model()


class StreamsOptOutColumnTests(TestCase):
    def _column_value(self, user):
        model_admin = CustomUserAdmin(User, AdminSite())
        request = RequestFactory().get("/admin/users/user/")
        row = model_admin.get_queryset(request).get(pk=user.pk)
        return model_admin.streams_opt_out(row)

    def test_excluded_user_shows_true(self):
        user = User.objects.create_user(username="optedout")
        SocialAccount.objects.create(user=user, provider="twitch", uid="123456789")
        TwitchExclusion.objects.create(twitch_id=123456789)
        self.assertIs(self._column_value(user), True)

    def test_linked_but_not_excluded_shows_false(self):
        user = User.objects.create_user(username="active")
        SocialAccount.objects.create(user=user, provider="twitch", uid="555")
        TwitchExclusion.objects.create(twitch_id=123456789)  # someone else
        self.assertIs(self._column_value(user), False)

    def test_no_twitch_account_shows_unknown(self):
        user = User.objects.create_user(username="localadmin")
        self.assertIsNone(self._column_value(user))
