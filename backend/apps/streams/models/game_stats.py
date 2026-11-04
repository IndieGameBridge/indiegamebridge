from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.streams.models.game import Game


class GameStats(models.Model):
    """Streams live in each hour of the last 4 weeks, for the Games page.

    One row per (game, language, streamer size group) with any streams in the window, so
    one row is one line on a game's chart. The language can also be ALL_LANGUAGES, and the
    size group ANY_SIZE. rebuild_game_stats replaces all the rows in one pass.

    `hours` and `streams` run side by side, newest first, and hold only the hours with
    streams. `position` is the row's place in its list, one list per language and size
    group, so a search reads a stored order instead of comparing 4 weeks of hours.
    """

    # The size group that adds every streamer up, the ones with no size yet included.
    # The groups themselves are numbered from 1, in the order of SIZE_GROUPS.
    ANY_SIZE = 0

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="hour_stats",
    )

    language = models.CharField(
        max_length=3,
        help_text="ISO 639-1 language code, or 'all' for every page language added up.",
    )

    size_group = models.PositiveSmallIntegerField(
        help_text="0 for every streamer, or the streamers' size group, numbered from 1.",
    )

    position = models.PositiveIntegerField(
        help_text="Place in this language's and size group's list: the game with the most streams"
            " in the newest hour comes first, and an older hour only breaks a tie.",
    )

    hours = ArrayField(
        models.IntegerField(),
        help_text="The hours with streams, newest first, each as whole hours since the Unix epoch.",
    )

    streams = ArrayField(
        models.IntegerField(),
        help_text="How many streams were live on the game in each of `hours`.",
    )

    class Meta:
        constraints = [
            # Also what reads one game's chart.
            models.UniqueConstraint(
                fields=["game", "language", "size_group"],
                name="unique_game_language_size_stats",
            ),
        ]
        indexes = [
            models.Index(fields=["language", "size_group", "position"], name="gamestats_list_idx"),
        ]

    def __str__(self):
        return f"GameStats(game_id={self.game_id}, language={self.language!r}, size_group={self.size_group})"
