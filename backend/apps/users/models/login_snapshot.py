from django.conf import settings
from django.db import models


class LoginSnapshot(models.Model):
    """One row per successful login (Twitch OAuth or admin password sign-in).

    Created by the user_logged_in receiver (apps.users.signals). The location
    fields are filled only when IPINFO_API_TOKEN is configured; otherwise they
    stay blank and the row still records who logged in, when, and from what IP.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_snapshots",
        help_text="The user who logged in.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the login happened (stored in UTC).",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP the login came from.",
    )

    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code, e.g. 'DE'.",
    )

    region = models.CharField(max_length=100, blank=True)

    city = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} @ {self.created_at:%Y-%m-%d %H:%M:%S} UTC"
