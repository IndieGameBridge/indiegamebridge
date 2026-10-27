from datetime import timedelta

from django.contrib import admin

from apps.fetch.models import FetchRun, FetchRunLanguage


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
class FetchRunAdmin(admin.ModelAdmin):
    """View only: fetch_twitch_streams writes these as it runs."""

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
