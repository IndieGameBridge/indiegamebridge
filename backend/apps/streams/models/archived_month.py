from django.contrib.postgres.fields import ArrayField
from django.db import models


class ArchivedMonth(models.Model):
    """One calendar month of finished streams, written by archive_streams to a
    Parquet file under ARCHIVE_DIR/streams once the month is over.

    A stream belongs to the month it finished in (UTC). Once a stream is finished
    its finished_at no longer changes, so a past month's file is complete: no stream
    can land in it after it has been written. Streams can leave it, though: the
    opt-out cleanup rewrites it without the streamers who opt out.

    The month stays in Postgres after its file is written; archive_streams deletes its
    streams a day at a time as they pass KEEP_DAYS, and counts its game history from
    the file into GameMonthStats.
    """

    month = models.DateField(
        unique=True,
        help_text="First day of the month whose streams the file holds, by when they finished (UTC).",
    )

    file_name = models.CharField(
        max_length=64,
        help_text="The file's name under ARCHIVE_DIR/streams, e.g. '2026-06.parquet'.",
    )

    streams_count = models.PositiveIntegerField(
        help_text="Streams in the file, checked against the row count the file itself records.",
    )

    first_stream_id = models.BigIntegerField(
        help_text="Lowest Stream id in the file.",
    )

    last_stream_id = models.BigIntegerField(
        help_text="Highest Stream id in the file. Checking that none of the month is left in Postgres"
            " only has to walk the ids between the two.",
    )

    file_size = models.PositiveBigIntegerField(
        help_text="Size of the file in bytes.",
    )

    sha256 = models.CharField(
        max_length=64,
        help_text="SHA-256 of the file, for checking a copy of it against the original.",
    )

    archived_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the file was written.",
    )

    deleted_through = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The month's streams that finished before this are deleted from Postgres; empty until the"
            " first of them is.",
    )

    rows_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last of the month's streams were deleted from Postgres; empty until then.",
    )

    rewritten_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the file was last rewritten without the streams of streamers who opted"
            " out; empty if never. Copies of the file made before then still hold them.",
    )

    stats_computed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the month's game history (GameMonthStats) was last counted from the file; empty until it is.",
    )

    stats_languages = ArrayField(
        models.CharField(max_length=3),
        default=list,
        blank=True,
        help_text="The page languages the game history's totals added up when it was counted. When the pages"
            " offer others, the month is counted again.",
    )

    class Meta:
        ordering = ("month",)

    def __str__(self):
        return f"ArchivedMonth: {self.month:%Y-%m} ({self.streams_count} streams)"
