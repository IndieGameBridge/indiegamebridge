"""allauth adapters.

OptOutSocialAccountAdapter intercepts the opt-out OAuth entry so that a visitor
who only wants to opt out never gets an account created for them. allauth's
auto-signup would otherwise persist a User during the OAuth callback, before our
finalize view runs.
"""

from urllib.parse import parse_qs, urlparse

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseRedirect

from apps.users.views.opt_out import perform_opt_out_for_twitch_id


class OptOutSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Standard adapter, except: when the social login was started from the
    opt-out flow (its `next` carries `action=optout`), verify the Twitch ID,
    record the opt-out, and short-circuit *before* allauth creates or logs in
    any account. Raising ImmediateHttpResponse here is the allauth-sanctioned
    way to abort the login (see DefaultSocialAccountAdapter.pre_social_login).

    Normal logins (no `action=optout` in `next`) are untouched.
    """

    def pre_social_login(self, request, sociallogin):
        next_url = sociallogin.state.get("next") or ""
        if "action=optout" not in next_url:
            return  # normal login - let allauth proceed

        is_new = perform_opt_out_for_twitch_id(sociallogin.account.uid)
        success_url = self._optout_success_url(next_url, is_new)
        raise ImmediateHttpResponse(HttpResponseRedirect(success_url))

    def _optout_success_url(self, finalize_next_url, is_new) -> str:
        """Build the absolute frontend success URL the browser should land on.

        `finalize_next_url` is the finalize URL the opt-out flow pointed at,
        e.g. `/auth/finalize-login/?action=optout&next=/optout?status=done`.
        We pull its inner `next` (the frontend path) and append `new=yes|no`,
        mirroring what the finalize view's opt-out branch produces.
        """
        frontend = settings.FRONTEND_URL.rstrip("/")
        inner = parse_qs(urlparse(finalize_next_url).query).get("next", [""])[0]
        # Only accept a same-site relative path; otherwise fall back. Prevents
        # an attacker-supplied absolute URL from turning this into an open redirect.
        if not inner.startswith("/"):
            inner = "/optout?status=done"
        separator = "&" if "?" in inner else "?"
        return f"{frontend}{inner}{separator}new={'yes' if is_new else 'no'}"
