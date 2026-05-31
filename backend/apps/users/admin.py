from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import User, TwitchExclusion, AccountSettings


admin.site.register(User, UserAdmin)


@admin.register(TwitchExclusion)
class TwitchExclusionAdmin(admin.ModelAdmin):
    list_display = ("twitch_id", "optout_at")
    search_fields = ("twitch_id",)
    ordering = ("-optout_at",)
    readonly_fields = ("optout_at",)


@admin.register(AccountSettings)
class AccountSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "allow_tracking")
    search_fields = ("user__username",)
