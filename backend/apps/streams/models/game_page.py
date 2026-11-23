from django.db import models

from apps.streams.models.game import Game


class GamePage(models.Model):
    """A game's public page, /game/<slug>: who streamed it on Twitch in the last 4 weeks.

    A game gets one the first time enough different streamers played it in the window
    (apps.streams.game_pages.PAGE_MIN_STREAMERS), and keeps it: when the game goes quiet, the
    row and its address stay, so a link to the page never breaks, and search engines may go on
    indexing it. While few streamers play it, the page shows totals only. rebuild_game_pages
    refreshes every row every 6 hours.
    """

    game = models.OneToOneField(
        Game,
        on_delete=models.CASCADE,
        related_name="page",
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="The page's address, /game/<slug>: made from the game's name when the page is, and never changed.",
    )

    name = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="The game's name as the pages show it: with its release year when another page's game has the same"
            " name, as in Resident Evil 4 (2005). Written by rebuild_game_pages.",
    )

    streamers = models.PositiveIntegerField(
        default=0,
        help_text="Different streamers who played it in the last 4 weeks. From DETAIL_MIN_STREAMERS the page shows"
            " more than totals.",
    )

    last_streamed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When its newest stream ended; kept once no stream of it is left in the window.",
    )

    numbers = models.JSONField(
        default=dict,
        blank=True,
        help_text="What the page shows besides the streamers, as rebuild_game_pages computed it: streams, hours,"
            " and from DETAIL_MIN_STREAMERS the languages, sizes, weeks, hours of the day and games also played.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the game got its page.",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When rebuild_game_pages last changed this row.",
    )

    def __str__(self):
        return f"GamePage: {self.slug} ({self.streamers} streamers)"
