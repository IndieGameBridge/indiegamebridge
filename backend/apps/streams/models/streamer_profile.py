from django.db import models


class StreamerProfile(models.Model):
    class Host(models.TextChoices):
        TWITCH = "twitch", "Twitch"

    host = models.CharField(
        max_length=16,
        choices=Host.choices,
        help_text="Host name"
    )

    host_user_id = models.BigIntegerField(
        help_text="User ID defined by host"
    )

    host_login = models.CharField(
        max_length=64,
        help_text="User login defined by host"
    )

    host_display_name = models.CharField(
        max_length=255,
        help_text="User display name defined by host"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Time of the latest update for the profile"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["host", "host_user_id"], name="unique_host_user"),
        ]
        indexes = [
            # A profile page finds its streamer by login. Not unique: Twitch hands a freed
            # login to a new account, so a few logins belong to two profiles.
            models.Index(fields=["host_login"], name="streamerprofile_login_idx"),
        ]

    def __str__(self):
        return f"Host: {self.host} | Host User ID: {self.host_user_id} - {self.host_display_name}"
