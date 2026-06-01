"""Opt-in helper: remove a user's Twitch ID from TwitchExclusion.

The inverse of perform_opt_out. Used by the logged-in StreamExclusionView
toggle on the Account Settings page; there's no standalone opt-in endpoint.
"""

from allauth.socialaccount.models import SocialAccount

from apps.users.models import TwitchExclusion


def perform_opt_in(user) -> bool | None:
    """Resolve the user's Twitch ID via allauth's SocialAccount and remove any
    matching TwitchExclusion. Returns True if an exclusion was deleted, False if
    the user was not excluded, or None if no Twitch account is linked.
    Idempotent: re-running when not excluded is a no-op.
    """
    social = SocialAccount.objects.filter(user=user, provider="twitch").first()
    if social is None:
        print("opt in requested but no twitch social account linked")
        return None

    deleted, _ = TwitchExclusion.objects.filter(twitch_id=social.uid).delete()
    return deleted > 0
