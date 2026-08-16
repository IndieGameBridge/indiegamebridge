from django.db import models

from apps.streams.models.game_genre import GameGenre


class GenreStats(models.Model):
    """Per-(genre, language) aggregate over the last 4 weeks, for the Genre Trends page.

    One row per (GameGenre, language). The language axis lets the page break each
    genre's activity down by broadcast language (English / French / German / Spanish) instead of
    lumping every language into a single bar. Each row carries two sets of counters:

    - The ``*`` (published) fields are the last fully completed cycle's values and
      are what the page reads. They only change when a build cycle finishes.
    - The ``draft_*`` fields are the in-progress cycle's running totals. The chunked
      rebuild_genre_stats command adds each chunk's contribution to them, then copies
      draft -> published and zeroes the draft when the streamer cursor wraps (one full
      pass over all streamers = one cycle).

    Because the rebuild partitions streamers into disjoint chunks, a streamer (and so
    its distinct-streamer contribution to a genre/language) is counted in exactly one
    chunk, so chunk contributions can simply be summed without cross-chunk de-duplication.
    """

    genre = models.ForeignKey(
        GameGenre,
        on_delete=models.CASCADE,
        related_name="stats",
    )
    language = models.CharField(
        max_length=2,
        help_text="ISO 639-1 two-letter language code these counters are scoped to.",
    )

    # Published counters - read by the page; swapped in only at end of a cycle.
    streams_count = models.PositiveBigIntegerField(
        default=0,
        help_text="Approved streams in the last 4 weeks that played at least one game of this genre."
            " A stream spanning several genres counts once toward each.",
    )
    streamers_count = models.PositiveBigIntegerField(
        default=0,
        help_text="Distinct streamers with at least one such stream in the window.",
    )
    total_duration_seconds = models.PositiveBigIntegerField(
        default=0,
        help_text="Genre's share of streamed seconds in the window, split per stream by the fraction of"
            " snapshots on this genre's games. Non-game time (e.g. Just Chatting) is excluded.",
    )
    computed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the published values were last swapped in (end of a full build cycle).",
    )

    # Draft counters - the in-progress cycle's running totals.
    draft_streams_count = models.PositiveBigIntegerField(default=0)
    draft_streamers_count = models.PositiveBigIntegerField(default=0)
    draft_total_duration_seconds = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = ("genre", "language")

    def __str__(self):
        return (
            f"GenreStats(genre_id={self.genre_id}, language={self.language!r},"
            f" streams={self.streams_count})"
        )


class GenreStatsBuildState(models.Model):
    """Singleton cursor for the chunked genre-stats rebuild.

    Mirrors SearchStatsRebuildState: holds the last StreamerProfile.id processed so
    each cron run continues where the last left off, wrapping to 0 once it runs past
    the end - which is also the signal to publish the accumulated draft.
    """

    last_profile_id = models.BigIntegerField(
        default=0,
        help_text="Highest StreamerProfile.id processed by the last rebuild chunk.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GenreStatsBuildState(last_profile_id={self.last_profile_id})"
