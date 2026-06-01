"""Auth-related view - Opt Out (authenticated POST)."""

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.db import transaction
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.streams.models import StreamerProfile
from apps.users.cookies import clear_jwt_cookies
from apps.users.models import TwitchExclusion


def perform_opt_out_for_twitch_id(twitch_id) -> bool:
    """Record the opt-out for a Twitch ID and erase the data collected for it.
    Returns True if a new exclusion was created, False if it already existed.
    Idempotent: re-running does not refresh optout_at.

    Works off the raw Twitch ID (not a User), so it can run during the OAuth
    opt-out flow before any account exists (see OptOutSocialAccountAdapter).

    Deleting the StreamerProfile cascades to its streams and cached profile
    payload. The query/page caches aren't FK-linked here; they expire on their
    own (hence the "up to an hour" note shown to the user).
    """
    with transaction.atomic():
        _, is_new_opt_out = TwitchExclusion.objects.get_or_create(twitch_id=twitch_id)
        StreamerProfile.objects.filter(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=twitch_id,
        ).delete()
    return is_new_opt_out


def perform_opt_out(user) -> bool | None:
    """Resolve the user's Twitch ID via allauth's SocialAccount and opt it out.
    Returns True if a new exclusion was created, False if already opted out, or
    None if no Twitch account is linked.
    """
    social = SocialAccount.objects.filter(user=user, provider="twitch").first()
    if social is None:
        print("opt out requested but no twitch social account linked")
        return None

    return perform_opt_out_for_twitch_id(social.uid)


@method_decorator(csrf_protect, name="dispatch")
class OptOutView(APIView):
    """Opt-out endpoint for users already authenticated via JWT cookie.
    Records the opt-out, blacklists the refresh token, and clears cookies so
    the next page load renders the logged-out state."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        perform_opt_out(user=request.user)
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass  # already expired or blacklisted - clearing cookies is still correct

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_jwt_cookies(response)
        return response
