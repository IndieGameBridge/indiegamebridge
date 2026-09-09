from django.db import models


class StreamerInList(models.Model):
    """One streamer's membership in a user's list, carrying that user's own notes.

    A model of its own rather than a plain many-to-many for two reasons. It holds
    the owner's per-streamer notes, and it outlives the streamer: opting out
    deletes the StreamerProfile, and SET_NULL leaves this row in place -
    anonymous, but still holding what its owner wrote about it.

    Nothing here caches the streamer's name. Doing so would render a list without
    a join, but a cached name is exactly what an opt-out is meant to erase, so the
    join is the honest implementation.
    """

    list_of_streamers = models.ForeignKey(
        "userlists.UserListOfStreamers",
        on_delete=models.CASCADE,
        related_name="entries",
        help_text="List this entry belongs to.",
    )

    streamer_profile = models.ForeignKey(
        "streams.StreamerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="list_entries",
        help_text="The streamer, or NULL once they opted out and their profile was"
            " removed. A NULL entry renders anonymized and keeps its notes.",
    )

    description = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="The owner's own note about this streamer - contact details, or"
            " what came of reaching out.",
    )

    added_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the streamer was added to the list.",
    )

    class Meta:
        constraints = [
            # Postgres treats NULLs as distinct, so this blocks a live streamer
            # appearing twice while letting several anonymized entries coexist.
            models.UniqueConstraint(
                fields=["list_of_streamers", "streamer_profile"],
                name="unique_streamer_per_list",
            ),
        ]
        # Oldest first, id breaking ties. Saving a search writes the whole list in
        # one go, so insertion order is the ranking the user saw on the results
        # page; reversing it would put the smallest streamers on top.
        ordering = ("added_at", "id")

    def __str__(self):
        streamer = (
            self.streamer_profile.host_display_name if self.streamer_profile else "(removed)"
        )
        return f"StreamerInList: {streamer} in {self.list_of_streamers.title}"
