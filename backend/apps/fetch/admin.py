from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Sum

from apps.fetch.graphs import fetch_graphs
from apps.fetch.models import FetchRun, FetchRunLanguage
from core.utils.admin_charts import GraphsAdminMixin
from core.utils.admin_export import CsvExportAdminMixin, last_line, seconds, utc_minute


def _as_duration(seconds):
    # 312.4 -> "0:05:12", as the archive commands print their run time; empty until set
    return "" if seconds is None else str(timedelta(seconds=round(seconds)))


class FetchRunLanguageInline(admin.TabularInline):
    model = FetchRunLanguage
    fields = (
        "language", "duration", "rounds", "requests", "helix", "write",
        "streams_fetched", "streams_excluded", "streams_duplicates", "streams_written",
        "streams_created", "profiles_created", "time_limit_hit", "error",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Duration")
    def duration(self, obj):
        return _as_duration(obj.duration_seconds)

    @admin.display(description="Helix (s)")
    def helix(self, obj):
        return f"{obj.helix_seconds:.1f}"

    @admin.display(description="Write (s)")
    def write(self, obj):
        return f"{obj.write_seconds:.1f}"


@admin.register(FetchRun)
class FetchRunAdmin(CsvExportAdminMixin, GraphsAdminMixin, admin.ModelAdmin):
    """View only: fetch_twitch_streams writes these as it runs. Graphs of them are a
    link away from the list, and the newest can be exported."""

    export_name = "fetch-runs"
    graphs_title = "Fetch run graphs"
    list_display = (
        "started_at", "status", "duration", "streams_collected",
        "streams_finalized", "streams_dropped", "time_limit_hit",
    )
    list_filter = ("status", "time_limit_hit")
    date_hierarchy = "started_at"
    inlines = (FetchRunLanguageInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Duration", ordering="duration_seconds")
    def duration(self, obj):
        return _as_duration(obj.duration_seconds)

    def graphs_context(self, request, days):
        return fetch_graphs(days, language=request.GET.get("lang", ""))

    def export_rows(self, size):
        """The newest runs, each with its Helix requests and its time on Helix and on writes,
        added up over its languages."""
        runs = (
            FetchRun.objects.annotate(
                language_count=Count("languages"),
                requests=Sum("languages__requests"),
                helix_seconds=Sum("languages__helix_seconds"),
                write_seconds=Sum("languages__write_seconds"),
            )
            .order_by("-started_at")[:size]
        )
        header = [
            "started_at_utc", "status", "duration_seconds", "time_limit_hit", "languages", "requests",
            "helix_seconds", "write_seconds", "streams_collected", "streams_finalized", "streams_dropped",
            "finalize_seconds", "error",
        ]
        return header, [
            [
                utc_minute(run.started_at),
                run.status,
                seconds(run.duration_seconds),
                "yes" if run.time_limit_hit else "no",
                run.language_count,
                run.requests,
                seconds(run.helix_seconds),
                seconds(run.write_seconds),
                run.streams_collected,
                run.streams_finalized,
                run.streams_dropped,
                seconds(run.finalize_seconds),
                last_line(run.error),
            ]
            for run in runs
        ]
