"""Helpers for setting/clearing JWT cookies on HTTP responses.

Both cookies are site-wide. The frontend middleware trades the refresh cookie
for a new access token on whatever request finds the access cookie gone - a
page load or an API call it proxies - so the refresh cookie has to come along
on every request. Don't scope it to the refresh endpoint's path: the browser
never requests that path itself, so the middleware would never see the cookie.
HttpOnly keeps both away from page scripts.
"""

from django.conf import settings

# The access cookie expires this long before its token, so a request never
# carries a token that runs out on its way to Django: once the cookie is gone,
# the frontend middleware refreshes first.
ACCESS_COOKIE_MARGIN_SECONDS = 60


def set_jwt_cookies(response, access_token: str, refresh_token: str | None = None):
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        access_token,
        max_age=(
            int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
            - ACCESS_COOKIE_MARGIN_SECONDS
        ),
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path="/",
    )
    if refresh_token is not None:
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            refresh_token,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=True,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
            path="/",
        )


def clear_jwt_cookies(response):
    response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path="/")
