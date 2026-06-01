from django.db import models

from apps.streams.models.streamer_profile import StreamerProfile


class StreamerProfileCache(models.Model):
    streamer_profile = models.OneToOneField(
        StreamerProfile,
        on_delete=models.CASCADE,
        related_name="profile_cache",
        help_text="Streamer whose profile payload this row caches."
    )

    content = models.JSONField(
        help_text="Cached profile payload (e.g. list of streams) returned to callers as-is."
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
        return f"StreamerProfileCache: profile={self.streamer_profile_id} (refreshed {self.refreshed_at:%Y-%m-%d %H:%M})"
