from datetime import timezone as dt_timezone

from allauth.socialaccount.models import SocialAccount
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import CharField, Exists, F, OuterRef, Window
from django.db.models.functions import Cast, Lag, RowNumber
from django.utils import formats

from apps.streams.models import GameGenre
from apps.streams.search import GENRE_FILTER_NAMES, StreamerSearch
from apps.users.models import User, TwitchExclusion, AccountSettings, LoginSnapshot, SearchSnapshot
from core.utils.admin_export import CsvExportAdminMixin, days_between, minutes_between, utc_minute

# A search's filters other than the genres, each with its column in the CSV file. The
# columns hold the values the form sends: "51-200" for a size, 5 for a minimum.
SEARCH_FILTER_COLUMNS = (
    ("lang", "language"),
    ("peak", "max_viewers"),
    ("avgmin", "avg_viewers_min"),
    ("avgmax", "avg_viewers_max"),
    ("streamsmin", "streams_min"),
    ("streamsmax", "streams_max"),
    ("hoursmin", "hours_min"),
    ("hoursmax", "hours_max"),
)


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
class LoginSnapshotAdmin(CsvExportAdminMixin, admin.ModelAdmin):
    """Rows are created by the login signal only - no adding or editing here.
    Deleting stays enabled on purpose: snapshots are user PII and admins may
    need to purge them. The newest can be exported for studying who comes back."""

    change_list_template = "admin/export/change_list.html"
    export_name = "logins"
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

    def export_rows(self, size):
        """The newest logins, each with which of its user's logins it is and how long after
        the one before. Both count every login on record, so a returning user shows as one
        even when their first login is older than the file's. No IP, name, region or city."""
        by_user = {"partition_by": [F("user_id")], "order_by": F("created_at").asc()}
        logins = (
            LoginSnapshot.objects.select_related("user")
            .annotate(
                login_number=Window(RowNumber(), **by_user),
                previous_login=Window(Lag("created_at"), **by_user),
            )
            .order_by("-created_at")[:size]
        )
        header = [
            "user", "logged_in_at_utc", "login_number", "days_since_previous_login",
            "user_joined_utc", "country", "staff",
        ]
        return header, [
            [
                login.user_id,
                utc_minute(login.created_at),
                login.login_number,
                days_between(login.previous_login, login.created_at),
                utc_minute(login.user.date_joined),
                login.country_code,
                "yes" if login.user.is_staff else "no",
            ]
            for login in logins
        ]


@admin.register(SearchSnapshot)
class SearchSnapshotAdmin(CsvExportAdminMixin, admin.ModelAdmin):
    """The search endpoint writes these - no adding or editing here. Deleting stays allowed,
    as for login snapshots: each row is one user's usage data. The newest can be exported
    for studying what people search for, and which searches find few streamers."""

    change_list_template = "admin/export/change_list.html"
    export_name = "searches"
    list_display = ("created_at_utc", "user", "search", "matches")
    search_fields = ("user__username",)
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Searched at (UTC)", ordering="created_at")
    def created_at_utc(self, obj):
        return _utc(obj.created_at)

    @admin.display(description="Search")
    def search(self, obj):
        """The filters that narrowed it, as the form names them."""
        described = StreamerSearch(obj.filters).describe()
        return "; ".join(f"{item['label']}: {item['value']}" for item in described) or "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def export_rows(self, size):
        """The newest searches, each with which of its user's searches it is and how many
        minutes after the one before, counting every search on record. A filter left open
        reads "any", and the genres picked are named. No username."""
        by_user = {"partition_by": [F("user_id")], "order_by": F("created_at").asc()}
        searches = (
            SearchSnapshot.objects.select_related("user")
            .annotate(
                search_number=Window(RowNumber(), **by_user),
                previous_search=Window(Lag("created_at"), **by_user),
            )
            .order_by("-created_at")[:size]
        )
        genre_names = dict(GameGenre.objects.values_list("host_genre_id", "host_name"))
        header = [
            "user", "searched_at_utc", "search_number", "minutes_since_previous_search", "matches",
            *(column for _, column in SEARCH_FILTER_COLUMNS), "genres", "staff",
        ]
        return header, [
            [
                search.user_id,
                utc_minute(search.created_at),
                search.search_number,
                minutes_between(search.previous_search, search.created_at),
                search.matches,
                *(search.filters.get(name, "any") for name, _ in SEARCH_FILTER_COLUMNS),
                _genres_text(search.filters, genre_names),
                "yes" if search.user.is_staff else "no",
            ]
            for search in searches
        ]


def _genres_text(filters: dict, genre_names: dict) -> str:
    """The genres a search narrowed to, by name, as "Strategy + Indie"; "any" for none."""
    picked = [filters.get(name, "any") for name in GENRE_FILTER_NAMES]
    return " + ".join(genre_names.get(genre, str(genre)) for genre in picked if genre != "any") or "any"


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
