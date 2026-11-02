from django.db import models

from apps.streams.models.game_genre import GameGenre


class GenreStats(models.Model):
    """Per-(genre, language) aggregate over the last 4 weeks, for the Genre Trends page.

    One row per (GameGenre, language) with any activity in the window. The language axis
    lets the page break each genre's activity down by broadcast language instead of
    lumping every language into a single bar. rebuild_genre_stats replaces all the rows
    in one pass, once a day.
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
        help_text="When rebuild_genre_stats computed these numbers.",
    )

    class Meta:
        unique_together = ("genre", "language")

    def __str__(self):
        return (
            f"GenreStats(genre_id={self.genre_id}, language={self.language!r},"
            f" streams={self.streams_count})"
        )
