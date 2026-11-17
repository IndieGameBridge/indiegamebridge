import hashlib
import json
from datetime import timedelta

from django.core.cache import cache
from django.db import models

# The same search again this soon counts once: a reload, Back to the results, or
# the first page again after paging on.
REPEAT_WINDOW = timedelta(minutes=30)

# One person's searches less than this far apart make one sitting.
SITTING_GAP = timedelta(minutes=30)


class SearchSnapshot(models.Model):
    """One streamer search: its filters, and how many streamers matched.

    Kept to see how the search gets used and where the demand is: the languages,
    sizes and genres people look for, and the searches that find few streamers.
    The search endpoint records the first page of each search, and only for users
    who allow feature-usage tracking. Deleted after 12 months.

    No row names who searched. A person's searches less than SITTING_GAP apart
    share a sitting, so a search narrowed or widened after a thin result still
    reads as one person's. Only the cache knows whose a sitting is, and only until
    SITTING_GAP after their last search; nothing links one sitting to the next.
    """

    sitting = models.PositiveBigIntegerField(
        help_text="The sitting the search was part of, numbered by its first search.",
    )

    filters = models.JSONField(
        help_text='The search, every filter spelled out; "any" for a filter left open.',
    )

    matches = models.PositiveIntegerField(
        help_text="Streamers the search matched, counting any past the most it shows.",
    )

    staff = models.BooleanField(
        default=False,
        help_text="Whether a staff member searched, so the site's own searches can be left out.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the search ran (stored in UTC).",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            # A sitting's searches in order: the admin's numbering.
            models.Index(fields=["sitting", "created_at"], name="users_search_sitting_idx"),
        ]

    def __str__(self):
        return f"Sitting {self.sitting} @ {self.created_at:%Y-%m-%d %H:%M:%S} UTC"

    @classmethod
    def record(cls, user, filters: dict, matches: int):
        """Store a search without its user, unless they ran the same one within REPEAT_WINDOW.

        Returns the new row, or None for a repeat.
        """
        search = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()
        repeat_key = f"search-repeat:{user.pk}:{search}"
        if cache.get(repeat_key):
            return None

        sitting_key = f"search-sitting:{user.pk}"
        sitting = cache.get(sitting_key)
        row = cls.objects.create(sitting=sitting or 0, filters=filters, matches=matches, staff=user.is_staff)
        if sitting is None:
            # A new sitting takes its first search's id, which no other sitting has.
            sitting = row.sitting = row.pk
            cls.objects.filter(pk=row.pk).update(sitting=sitting)

        cache.set(repeat_key, True, int(REPEAT_WINDOW.total_seconds()))
        cache.set(sitting_key, sitting, int(SITTING_GAP.total_seconds()))
        return row
