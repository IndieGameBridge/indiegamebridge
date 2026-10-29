from django.contrib import admin

from apps.exports.graphs import export_graphs
from apps.exports.models import Export
from core.utils.admin_charts import GraphsAdminMixin


@admin.register(Export)
class ExportAdmin(GraphsAdminMixin, admin.ModelAdmin):
    """The export endpoints write these. Deleting stays allowed, as for login
    snapshots: each row is one user's usage data. Graphs of them are a link away
    from the list."""

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
