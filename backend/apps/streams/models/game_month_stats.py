from django.db import models

from apps.streams.models.game import Game


class GameMonthStats(models.Model):
    """A game on Twitch in one past month: the history behind the game pages.

    Counted from the month's archive file, once, right after archive_streams writes it, and
    again only when the file is rewritten or the page languages change. One row per (game,
    month, language) with any approved streams of it, in every language collected, plus one
    per (game, month) for the page languages added up, under ALL_LANGUAGES.

    The numbers count as the game pages do: a stream counts for every game it played, and only
    categories IGDB lists as games count. A streamer counts once per row, however many of their
    streams it holds.
    """

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="month_stats",
        # The unique constraint leads with this column, so it serves lookups by game.
        db_index=False,
    )

    month = models.DateField(
        help_text="First day of the month, by when the streams finished (UTC).",
    )

    language = models.CharField(
        max_length=3,
        help_text="ISO 639-1 language code, or 'all' for the page languages added up.",
    )

    streamers = models.PositiveIntegerField(
        help_text="Different streamers who played the game that month.",
    )

    streams = models.PositiveIntegerField(
        help_text="Their streams that played it.",
    )

    seconds = models.PositiveBigIntegerField(
        help_text="Time played: each stream's length split evenly between all the categories it played, as the"
            " game pages count hours.",
    )

    viewer_seconds = models.PositiveBigIntegerField(
        help_text="Time watched: each snapshot on the game, its viewers times the snapshot's share of its"
            " stream's length, added up.",
    )

    snapshot_seconds = models.PositiveBigIntegerField(
        help_text="The stream time the snapshots saw on the game, each snapshot's share of its stream's length."
            " viewer_seconds / snapshot_seconds is the average viewers while the game was played.",
    )

    class Meta:
        constraints = [
            # Also what reads one game's history, a language at a time, in month order.
            models.UniqueConstraint(fields=["game", "language", "month"], name="unique_game_language_month"),
        ]

    def __str__(self):
        return f"GameMonthStats(game_id={self.game_id}, {self.month:%Y-%m}, {self.language!r})"
