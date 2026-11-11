from django.contrib import admin
from django.db.models import F, Window
from django.db.models.functions import Lag, RowNumber

from apps.exports.graphs import export_graphs
from apps.exports.models import Export
from core.utils.admin_charts import GraphsAdminMixin
from core.utils.admin_export import CsvExportAdminMixin, days_between, utc_minute


@admin.register(Export)
class ExportAdmin(CsvExportAdminMixin, GraphsAdminMixin, admin.ModelAdmin):
    """The export endpoints write these. Deleting stays allowed, as for login
    snapshots: each row is one user's usage data. Graphs of them are a link away
    from the list, and the newest can be exported."""

    export_name = "exports"
    graphs_title = "Export graphs"
    list_display = ("created_at", "user", "source", "list_of_streamers", "file_format", "rows")
    list_filter = ("source", "file_format")
    search_fields = ("user__username", "list_of_streamers__title")
    list_select_related = ("user", "list_of_streamers")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def graphs_context(self, request, days):
        return export_graphs(days)

    def export_rows(self, size):
        """The newest exports, each with which of its user's exports it is and how long after
        the one before, counting every export on record. A list is its number, not its title."""
        by_user = {"partition_by": [F("user_id")], "order_by": F("created_at").asc()}
        exports = (
            Export.objects.annotate(
                export_number=Window(RowNumber(), **by_user),
                previous_export=Window(Lag("created_at"), **by_user),
            )
            .order_by("-created_at")[:size]
        )
        header = [
            "user", "exported_at_utc", "export_number", "days_since_previous_export",
            "source", "list", "file_format", "rows", "search",
        ]
        return header, [
            [
                export.user_id,
                utc_minute(export.created_at),
                export.export_number,
                days_between(export.previous_export, export.created_at),
                export.source,
                export.list_of_streamers_id,
                export.file_format,
                export.rows,
                _search_text(export.search_filters),
            ]
            for export in exports
        ]


def _search_text(search_filters) -> str:
    """A search's filters as "lang=en peak=51-200 avgmin=5", leaving out those set to "any"."""
    return " ".join(
        f"{name}={value}" for name, value in (search_filters or {}).items() if value not in ("any", None, "", [])
    )
