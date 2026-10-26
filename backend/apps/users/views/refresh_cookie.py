"""Auth-related view - Refresh Cookie."""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.cookies import set_jwt_cookies

# How long a just-rotated refresh token still gets the same answer. Requests
# that leave the browser together - a page and its prefetches, a few API calls,
# two tabs - all carry the old token; without this, every one after the first
# finds it blacklisted and the user is logged out. Whoever holds the old token
# within this window gets the new pair, which is the usual trade-off.
ROTATION_GRACE_SECONDS = 30


@method_decorator(csrf_protect, name="dispatch")
class RefreshCookieView(APIView):
    """Reads the refresh token from its cookie, issues a new access cookie (and
    rotated refresh cookie). Body stays empty - the frontend never touches
    tokens directly."""

    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw_refresh:
            raise InvalidToken("No refresh cookie present.")

        # A hash keeps the key short, and the old token out of the cache.
        cache_key = "jwt-refreshed:" + hashlib.sha256(raw_refresh.encode()).hexdigest()
        try:
            refresh = RefreshToken(raw_refresh)
        except TokenError as exc:
            # Spent moments ago by a request that left the browser with this
            # same token: give the same answer.
            tokens = cache.get(cache_key)
            if tokens is None:
                raise InvalidToken(str(exc)) from exc
        else:
            tokens = self._rotate(refresh, raw_refresh, cache_key)

        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_jwt_cookies(response, *tokens)
        return response

    @staticmethod
    def _rotate(refresh: RefreshToken, raw_refresh: str, cache_key: str) -> tuple[str, str | None]:
        access_token = str(refresh.access_token)
        if not settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"):
            return access_token, None

        # A copy becomes the new token, so the old one can still be blacklisted
        # after the new pair is cached. It was verified just above.
        rotated = RefreshToken(raw_refresh, verify=False)
        rotated.set_jti()
        rotated.set_exp()
        rotated.set_iat()
        tokens = (access_token, str(rotated))

        # Cached before the blacklisting: a request that finds the old token
        # blacklisted always finds this answer too.
        cache.set(cache_key, tokens, ROTATION_GRACE_SECONDS)
        if settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"):
            try:
                refresh.blacklist()
            except AttributeError:
                pass  # blacklist app not installed
        return tokens
