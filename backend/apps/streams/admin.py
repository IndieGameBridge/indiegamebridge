from django.contrib import admin
from django.template.defaultfilters import filesizeformat

from apps.streams.models import ArchivedMonth, JsonCache, Stream, StreamerProfileCache


admin.site.register(Stream)


@admin.register(ArchivedMonth)
class ArchivedMonthAdmin(admin.ModelAdmin):
    """View only: archive_streams writes these, and a record removed by hand would
    leave its file on disk with nothing pointing at it."""

    list_display = ("month", "streams_count", "size", "archived_at", "rows_deleted_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Size", ordering="file_size")
    def size(self, obj):
        return filesizeformat(obj.file_size)


@admin.register(JsonCache)
class JsonCacheAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    readonly_fields = ("updated_at",)
    search_fields = ("key",)


@admin.register(StreamerProfileCache)
class StreamerProfileCacheAdmin(admin.ModelAdmin):
    list_display = ("streamer_profile", "refreshed_at", "last_hit_at", "created_at")
    readonly_fields = ("streamer_profile", "content", "created_at", "refreshed_at", "last_hit_at")
    search_fields = ("streamer_profile__host_login", "streamer_profile__host_display_name")
    ordering = ("-refreshed_at",)
