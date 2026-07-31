from django.conf import settings
from django.db import models


class AccountSettings(models.Model):
    """Account-wide preferences for a logged-in user.

    One row per user (created lazily on first access). Holds generic toggles
    that aren't part of identity/auth. Role-specific settings (streamer /
    developer) can move to dedicated models if and when those features exist.

    Note: the Twitch streams opt-out is intentionally NOT stored here - it
    lives in TwitchExclusion, keyed by Twitch ID and queried by the streams
    poll independently of the user record.

    allow_tracking also gates login bookkeeping (LoginSnapshot rows and the
    last_login timestamp) - see apps.users.signals.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings",
        help_text="The user these settings belong to."
    )

    allow_tracking = models.BooleanField(
        default=True,
        help_text="If True, the user's feature-usage analytics are collected."
    )

    def __str__(self):
        return f"AccountSettings for {self.user}"
