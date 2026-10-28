from django.conf import settings
from django.db import models


class Export(models.Model):
    """One file a user exported: a list or a search, as Excel, CSV or JSON.

    Kept to see how exports get used: which formats, and whether people come
    back to export the same list again once their copy has gone stale. Recorded
    only for users who allow feature-usage tracking, and deleted with the account.
    """

    class Source(models.TextChoices):
        LIST = "list", "List"
        SEARCH = "search", "Search"

    class FileFormat(models.TextChoices):
        XLSX = "xlsx", "Excel"
        CSV = "csv", "CSV"
        JSON = "json", "JSON"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exports",
        help_text="Who exported the file.",
    )

    source = models.CharField(
        max_length=8,
        choices=Source.choices,
        help_text="Whether a list or a search was exported.",
    )

    list_of_streamers = models.ForeignKey(
        "userlists.UserListOfStreamers",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exports",
        help_text="The list exported; empty for a search, and once the list is deleted.",
    )

    search_filters = models.JSONField(
        default=dict,
        blank=True,
        help_text="The search exported, every filter spelled out; empty for a list.",
    )

    file_format = models.CharField(
        max_length=8,
        choices=FileFormat.choices,
        help_text="The file's format.",
    )

    rows = models.PositiveIntegerField(
        help_text="Streamers in the file.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the file was exported.",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Export: {self.get_source_display()} as {self.get_file_format_display()} by {self.user}"
