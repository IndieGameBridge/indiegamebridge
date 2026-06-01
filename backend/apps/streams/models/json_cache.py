from django.db import models


class JsonCache(models.Model):
    """Generic key -> JSON store for ad-hoc streams-side caches.

    Use when a feature needs to cache a small JSON payload but doesn't warrant
    its own model (no special columns, indexes, or eviction semantics). Each
    feature defines its own key string and TTL on top of this table.
    """

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable identifier for this cache entry (e.g. 'streamers_distribution')."
            " Used as the lookup key by readers."
    )

    content = models.JSONField(
        help_text="Cached JSON payload returned to callers as-is."
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Time of the latest cache refresh for this entry."
            " TTL freshness is evaluated against this value."
    )

    def __str__(self):
        return f"JsonCache: {self.key} (updated {self.updated_at:%Y-%m-%d %H:%M})"
