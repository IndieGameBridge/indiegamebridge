from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from apps.streams.models.streamer_profile import StreamerProfile


class StreamerSearchStats(models.Model):
    """Precomputed per-streamer, per-language search row.

    Search reads this narrow table directly instead of scanning and aggregating
    the wide streams table. One row per (streamer, language). Rebuilt in rolling
    chunks by the rebuild_search_stats command, so values are roughly a day
    stale - an accepted trade for fast, predictable search.
    """

    streamer_profile = models.ForeignKey(
        StreamerProfile,
        on_delete=models.CASCADE,
        related_name="search_stats",
    )

    language = models.CharField(
        max_length=2,
        help_text="ISO 639-1 language code; one row per (streamer, language) pair.",
    )

    peak_viewers = models.PositiveIntegerField(
        help_text="Max peak viewers across the streamer's approved streams in the last 4 weeks.",
    )

    avg_viewers = models.PositiveIntegerField(
        help_text="Mean of per-stream avg viewers over the same streams, rounded.",
    )

    total_duration_seconds = models.PositiveIntegerField(
        help_text="Total streamed seconds over the same streams; shown as 'X hours in last 4 weeks'.",
    )

    streams_count = models.PositiveIntegerField(
        help_text="Number of approved streams contributing to this row.",
    )

    genre_ids = ArrayField(
        models.BigIntegerField(),
        default=list,
        blank=True,
        help_text="Distinct GameGenre.host_genre_id values played in the window; filtered by overlap.",
    )

    # Denormalized from StreamerProfile so search renders without a join. May lag
    # a rename until the next rebuild of this row.
    host_login = models.CharField(max_length=64)
    host_display_name = models.CharField(max_length=255)

    computed_at = models.DateTimeField(
        auto_now=True,
        help_text="When this row was last recomputed.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["streamer_profile", "language"],
                name="unique_streamer_language_stats",
            ),
        ]
        indexes = [
            # language-leading so a per-language search walks one slice already in
            # the result sort order (peak, then avg), serving ORDER BY + LIMIT.
            models.Index(fields=["language", "-peak_viewers", "-avg_viewers"], name="searchstats_lang_peak_idx"),
            models.Index(fields=["language", "-avg_viewers"], name="searchstats_lang_avg_idx"),
            models.Index(fields=["language", "-total_duration_seconds"], name="searchstats_lang_dur_idx"),
            GinIndex(fields=["genre_ids"], name="searchstats_genre_ids_gin"),
        ]

    def __str__(self):
        return f"SearchStats: {self.host_login} [{self.language}] (computed {self.computed_at:%Y-%m-%d %H:%M})"


class SearchStatsRebuildState(models.Model):
    """Singleton cursor for the chunked search-stats rebuild.

    Holds the last StreamerProfile.id processed so each cron run continues where
    the previous left off, wrapping back to 0 once it runs past the end.
    """

    last_profile_id = models.BigIntegerField(
        default=0,
        help_text="Highest StreamerProfile.id processed by the last rebuild chunk.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SearchStatsRebuildState(last_profile_id={self.last_profile_id})"
