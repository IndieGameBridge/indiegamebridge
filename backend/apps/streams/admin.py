from django.contrib import admin

from apps.streams.models import JsonCache, SearchCache, Stream, StreamerProfileCache


admin.site.register(Stream)


@admin.register(SearchCache)
class SearchCacheAdmin(admin.ModelAdmin):
    list_display = ("key_hash_short", "refreshed_at", "last_hit_at", "created_at")
    readonly_fields = ("key_hash", "filters", "results", "created_at", "refreshed_at", "last_hit_at")
    search_fields = ("key_hash",)
    ordering = ("-refreshed_at",)

    @admin.display(description="key_hash")
    def key_hash_short(self, obj):
        return f"{obj.key_hash[:12]}…"


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
