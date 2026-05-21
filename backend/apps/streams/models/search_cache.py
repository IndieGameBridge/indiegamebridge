from django.db import models


class SearchCache(models.Model):
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="Deterministic hash of the normalized filter set."
            " Two requests representing the same search share one row."
    )

    filters = models.JSONField(
        help_text="Normalized filter values that produced this entry."
            " Kept for debugging/inspection; not used for lookup (key_hash is)."
    )

    results = models.JSONField(
        help_text="Cached search payload returned to the frontend as-is."
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this entry was first computed."
    )

    refreshed_at = models.DateTimeField(
        auto_now=True,
        help_text="Time of the latest recompute for this entry."
            " TTL freshness is evaluated against this value."
    )

    last_hit_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Updated every time the entry is read."
            " Used by eviction to drop entries no one queries anymore."
    )

    def __str__(self):
        return f"SearchCache: {self.key_hash[:12]}… (refreshed {self.refreshed_at:%Y-%m-%d %H:%M})"
