from django.conf import settings
from django.db import models


class UserListOfStreamers(models.Model):
    """A named, user-owned collection of streamers, shown as a card on the dashboard.

    The streamers themselves live in a separate membership model rather than a
    plain M2M, so each entry can carry the owner's own notes and survive - as an
    anonymized row - a streamer opting out.

    Lists are private to their owner. Titles are not unique for the same reason
    label titles aren't: two lists can reasonably share a name while their
    descriptions and labels tell them apart.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="streamer_lists",
        help_text="User this list belongs to; lists are private to their owner.",
    )

    title = models.CharField(
        max_length=32,
        help_text="Name shown on the list card, e.g. 'small shooter streamers'.",
    )

    description = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="The owner's own note about what the list is for.",
    )

    labels = models.ManyToManyField(
        "userlists.UserLabelForListOfStreamers",
        blank=True,
        related_name="lists",
        help_text="Owner's labels for this list. Nothing at the database level ties a"
            " label's owner to the list's owner - the write endpoints have to.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the list was created.",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the list's own fields last changed. Adding or removing"
            " streamers touches the membership rows, not this.",
    )

    class Meta:
        # Newest first: saving a search sends the user straight to the dashboard,
        # where the list they just made should be the first card. -id breaks ties,
        # since created_at only resolves to the OS clock's granularity and two
        # lists made in the same tick would otherwise come back in any order.
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"UserListOfStreamers: {self.title} of {self.owner}"
