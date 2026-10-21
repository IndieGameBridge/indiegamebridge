"""Tests for RefreshCookieView: rotation, the grace window for concurrent
refreshes, and the cookies it sets."""

from http.cookies import SimpleCookie
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.users.cookies import ACCESS_COOKIE_MARGIN_SECONDS

User = get_user_model()

ACCESS = settings.JWT_ACCESS_COOKIE_NAME
REFRESH = settings.JWT_REFRESH_COOKIE_NAME


class RefreshCookieTests(TestCase):
    def setUp(self):
        cache.clear()  # the grace window and the throttle counters live there
        self.user = User.objects.create_user(username="viewer")
        self.refresh = str(RefreshToken.for_user(self.user))

    def _refresh(self, raw_refresh):
        # A fresh jar: the client's shares cookie objects with earlier responses,
        # so setting a value in it would rewrite what those responses set.
        self.client.cookies = SimpleCookie({REFRESH: raw_refresh})
        return self.client.post(reverse("auth-token-refresh"))

    def test_rotates_the_refresh_token_and_blacklists_the_old_one(self):
        response = self._refresh(self.refresh)

        self.assertEqual(response.status_code, 204)
        rotated = response.cookies[REFRESH].value
        self.assertNotEqual(rotated, self.refresh)
        self.assertEqual(str(AccessToken(response.cookies[ACCESS].value)["user_id"]), str(self.user.id))
        old_jti = RefreshToken(self.refresh, verify=False)["jti"]
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_jti).exists())
        # The new one works in turn.
        self.assertEqual(self._refresh(rotated).status_code, 204)

    def test_refreshing_again_with_the_spent_token_gets_the_same_pair(self):
        first = self._refresh(self.refresh)
        second = self._refresh(self.refresh)

        self.assertEqual(second.status_code, 204)
        self.assertEqual(second.cookies[ACCESS].value, first.cookies[ACCESS].value)
        self.assertEqual(second.cookies[REFRESH].value, first.cookies[REFRESH].value)

    def test_spent_token_is_rejected_after_the_grace_window(self):
        self._refresh(self.refresh)
        cache.clear()  # the grace window ran out

        self.assertEqual(self._refresh(self.refresh).status_code, 401)

    def test_a_refresh_right_after_the_blacklisting_gets_the_new_pair(self):
        # The second request arrives the moment the first has blacklisted the
        # token, before it has answered.
        blacklist = RefreshToken.blacklist
        concurrent = []

        def blacklist_then_refresh_again(token):
            result = blacklist(token)
            concurrent.append(self._refresh(self.refresh))
            return result

        with mock.patch.object(
            RefreshToken, "blacklist", autospec=True, side_effect=blacklist_then_refresh_again
        ):
            first = self._refresh(self.refresh)

        self.assertEqual(concurrent[0].status_code, 204)
        self.assertEqual(concurrent[0].cookies[REFRESH].value, first.cookies[REFRESH].value)

    def test_logged_out_token_is_rejected(self):
        RefreshToken(self.refresh).blacklist()

        self.assertEqual(self._refresh(self.refresh).status_code, 401)

    def test_missing_or_invalid_token_is_rejected(self):
        self.assertEqual(self.client.post(reverse("auth-token-refresh")).status_code, 401)
        self.assertEqual(self._refresh("not-a-token").status_code, 401)

    def test_cookies_are_site_wide_and_the_access_one_ends_before_its_token(self):
        response = self._refresh(self.refresh)

        access, refresh = response.cookies[ACCESS], response.cookies[REFRESH]
        # The frontend middleware refreshes on any request, so both must reach it.
        self.assertEqual(access["path"], "/")
        self.assertEqual(refresh["path"], "/")
        self.assertTrue(access["httponly"])
        self.assertTrue(refresh["httponly"])
        lifetime = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
        self.assertEqual(access["max-age"], lifetime - ACCESS_COOKIE_MARGIN_SECONDS)
