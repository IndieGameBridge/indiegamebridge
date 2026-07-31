from datetime import timezone as dt_timezone

from allauth.socialaccount.models import SocialAccount
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import CharField, Exists, OuterRef
from django.db.models.functions import Cast
from django.utils import formats

from apps.users.models import User, TwitchExclusion, AccountSettings, LoginSnapshot


def _utc(value):
    if not value:
        return "-"
    # Django's standard datetime rendering, e.g. "June 11, 2026, 12:18 p.m."
    return formats.date_format(value.astimezone(dt_timezone.utc), "DATETIME_FORMAT")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # UserAdmin.list_display minus last_name (field kept, just not shown -
    # it's unused for Twitch-login accounts).
    list_display = (
        "username",
        "email",
        "first_name",
        "is_staff",
        "date_joined",
        "last_login_utc",
        "streams_opt_out",
    )

    def get_queryset(self, request):
        # TwitchExclusion is keyed by Twitch UID, not a user FK - bridge via
        # the allauth SocialAccount. twitch_id (bigint) is cast to text for
        # the uid comparison; the reverse cast could error on a non-numeric
        # uid, this direction never can.
        qs = super().get_queryset(request)
        twitch_account = SocialAccount.objects.filter(
            user=OuterRef("pk"), provider="twitch"
        )
        excluded_ids = TwitchExclusion.objects.annotate(
            tid=Cast("twitch_id", CharField())
        ).values("tid")
        return qs.annotate(
            has_twitch=Exists(twitch_account),
            twitch_excluded=Exists(twitch_account.filter(uid__in=excluded_ids)),
        )

    @admin.display(description="Last login", ordering="last_login")
    def last_login_utc(self, obj):
        return _utc(obj.last_login)

    @admin.display(description="Streams opt-out", boolean=True, ordering="twitch_excluded")
    def streams_opt_out(self, obj):
        if not obj.has_twitch:
            return None  # no Twitch account linked - renders as "unknown"
        return obj.twitch_excluded


@admin.register(LoginSnapshot)
class LoginSnapshotAdmin(admin.ModelAdmin):
    """Rows are created by the login signal only - no adding or editing here.
    Deleting stays enabled on purpose: snapshots are user PII and admins may
    need to purge them."""

    list_display = ("user", "created_at_utc", "ip_address", "location")
    search_fields = ("user__username", "ip_address")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Logged in at (UTC)", ordering="created_at")
    def created_at_utc(self, obj):
        return _utc(obj.created_at)

    @admin.display(description="Location")
    def location(self, obj):
        parts = [p for p in (obj.city, obj.region, obj.country_code) if p]
        return ", ".join(parts) or "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
