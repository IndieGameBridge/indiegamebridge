from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# The same search again this soon counts once: a reload, Back to the results, or
# the first page again after paging on.
REPEAT_WINDOW = timedelta(minutes=30)


class SearchSnapshot(models.Model):
    """One streamer search a user ran: its filters, and how many streamers matched.

    Kept to see how the search gets used and where the demand is: the languages,
    sizes and genres people look for, and the searches that find few streamers.
    The search endpoint records the first page of each search, and only for users
    who allow feature-usage tracking. Deleted after 12 months, and with the account.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_snapshots",
        # The index below starts with the user, so it serves lookups by user too.
        db_index=False,
        help_text="Who searched.",
    )

    filters = models.JSONField(
        help_text='The search, every filter spelled out; "any" for a filter left open.',
    )

    matches = models.PositiveIntegerField(
        help_text="Streamers the search matched, counting any past the most it shows.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the search ran (stored in UTC).",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            # A user's recent searches: the repeat check, and the admin's numbering.
            models.Index(fields=["user", "created_at"], name="users_search_user_time_idx"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.created_at:%Y-%m-%d %H:%M:%S} UTC"

    @classmethod
    def record(cls, user, filters: dict, matches: int):
        """Store a search, unless the user ran the same one within REPEAT_WINDOW.

        Returns the new row, or None for a repeat.
        """
        recent = timezone.now() - REPEAT_WINDOW
        if cls.objects.filter(user=user, filters=filters, created_at__gte=recent).exists():
            return None
        return cls.objects.create(user=user, filters=filters, matches=matches)
