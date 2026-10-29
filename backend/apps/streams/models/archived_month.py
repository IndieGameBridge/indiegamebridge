from django.db import models


class ArchivedMonth(models.Model):
    """One calendar month of finished streams, written by archive_streams to a
    Parquet file under ARCHIVE_DIR/streams.

    A stream belongs to the month it finished in (UTC). Once a stream is finished
    its finished_at no longer changes, so a past month's file is complete: no stream
    can land in it after it has been written. Streams can leave it, though:
    remove_opted_out_from_archive rewrites it without the streamers who opt out.
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
        help_text="Highest Stream id in the file. Removing the month from Postgres only has to"
            " walk the ids between the two.",
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

    rows_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the month's streams were deleted from Postgres; empty until then.",
    )

    rewritten_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the file was last rewritten without the streams of streamers who opted"
            " out; empty if never. Copies of the file made before then still hold them.",
    )

    class Meta:
        ordering = ("month",)

    def __str__(self):
        return f"ArchivedMonth: {self.month:%Y-%m} ({self.streams_count} streams)"
