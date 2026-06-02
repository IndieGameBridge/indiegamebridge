import hashlib
import json
import logging
from datetime import timedelta
from functools import cache

from django.contrib.postgres.aggregates import JSONBAgg
from django.db import connection, transaction
from django.db.models import Avg, Count, F, Max, Sum
from django.db.models.functions import ExtractIsoWeekDay
from django.utils import timezone

from apps.streams.models import Game, SearchCache, Stream, GameGenre

logger = logging.getLogger(__name__)


SEARCH_CACHE_TTL = timedelta(hours=1)

# Hard cap on results stored per cache row. Sized so a single search returns
# up to MAX_RESULTS streamers; the API then slices this into pages of PAGE_SIZE.
MAX_RESULTS = 1000
PAGE_SIZE = 50


class StreamerSearch:
    """Single entry point for streamer search.

    Responsibilities:
      - Define the canonical default filters (used by the home page and as the default for `/streamers`).
      - Normalize incoming filters into a deterministic shape so equivalent
        searches share one cache entry.
      - Read/write the SearchCache with TTL-on-read semantics.
      - Run the underlying aggregation query against `Stream`.
    """

    def __init__(self, filters: dict | None = None):
        self.raw_filters = filters or {}
        self.filters = self._normalize_query_params(self.raw_filters)
        self.key_hash = self._hash(self.filters)
        self._full_results: list[dict] | None = None

    def results(self, offset: int = 0, limit: int = PAGE_SIZE) -> list[dict]:
        return self._get_full_results()[offset:offset + limit]

    def total(self) -> int:
        return len(self._get_full_results())

    def _get_full_results(self) -> list[dict]:
        if self._full_results is not None:
            return self._full_results

        # Fast path: a fresh entry is served without taking any lock.
        fresh = self._read_fresh()
        if fresh is not None:
            logger.debug("Search cache hit: %s", self.key_hash[:12])
            self._full_results = fresh
            return self._full_results

        # Miss or stale: serialize the recompute so concurrent identical
        # searches don't each run the (up to ~minute-long) aggregation.
        self._full_results = self._compute_single_flight()
        return self._full_results

    def _read_fresh(self) -> list[dict] | None:
        """Return cached results if a within-TTL entry exists, else None.

        Touches last_hit_at (used by future eviction) on a hit.
        """
        now = timezone.now()
        cached = SearchCache.objects.filter(key_hash=self.key_hash).first()
        if cached and (now - cached.refreshed_at) < SEARCH_CACHE_TTL:
            SearchCache.objects.filter(pk=cached.pk).update(last_hit_at=now)
            return cached.results
        return None

    def _compute_single_flight(self) -> list[dict]:
        """Recompute under a per-key Postgres advisory lock.

        Only one request per key runs the query at a time; others block on the
        lock and, once it releases, find the entry the holder just wrote. The
        lock is transaction-scoped, so it's released automatically on commit or
        rollback - a crashing worker can't leave it stuck.
        """
        if connection.vendor != "postgresql":
            # Advisory locks are Postgres-only; elsewhere (e.g. sqlite) fall back
            # to the unguarded recompute rather than failing.
            return self._recompute()

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [self._lock_key()])

            # Double-check: a request we queued behind may have filled the cache
            # while we waited for the lock.
            fresh = self._read_fresh()
            if fresh is not None:
                logger.debug("Search cache filled while waiting: %s", self.key_hash[:12])
                return fresh

            return self._recompute()

    def _recompute(self) -> list[dict]:
        # update_or_create resolves the row write into a single row even if two
        # recomputes ever race (e.g. on a non-Postgres backend without the lock).
        logger.debug("Search cache recompute: %s", self.key_hash[:12])
        fresh = self._run_query(self.filters)
        SearchCache.objects.update_or_create(
            key_hash=self.key_hash,
            defaults={
                "filters": self.filters,
                "results": fresh,
                "last_hit_at": timezone.now(),
            },
        )
        return fresh

    def _lock_key(self) -> int:
        # pg_advisory_xact_lock takes a signed 64-bit int; fold the hex digest
        # into that range. Collisions only cause two unrelated searches to
        # occasionally serialize - harmless, and astronomically rare at 64 bits.
        value = int(self.key_hash[:16], 16)
        return value - 2**64 if value >= 2**63 else value

    @classmethod
    def _normalize_query_params(cls, raw: dict) -> dict:
        normalized_filters = {}
        filters_config, allowed_names = cls.get_filters_config()

        # Trust only configuration names and values. "any" sentinels are dropped
        # from the normalized dict so the cache key stays stable across
        # equivalent "no-filter" requests and so _run_query can use simple
        # `key in filters` checks. Raw values arrive as strings from request.GET
        # but allowed_values are typed (e.g. int 100, not "100"), so we resolve
        # by string-equality and return the typed counterpart.
        def coerce(value, allowed_values):
            if value in allowed_values:
                return value
            str_value = str(value)
            for one_allowed in allowed_values:
                if str(one_allowed) == str_value:
                    return one_allowed
            return None

        def apply(field_name: str, allowed_values: list, default, multi: bool = False):
            if field_name not in allowed_names:
                return
            if field_name in raw:
                raw_value = raw[field_name]
                if multi:
                    source = raw_value if isinstance(raw_value, list) else [raw_value]
                    resolved = []
                    for one_raw in source:
                        rv = coerce(one_raw, allowed_values)
                        if rv is not None and rv != "any" and rv not in resolved:
                            resolved.append(rv)
                    if resolved:
                        normalized_filters[field_name] = resolved
                        return
                else:
                    rv = coerce(raw_value, allowed_values)
                    if rv is not None:
                        if rv != "any":
                            normalized_filters[field_name] = rv
                        return
            if default != "any":
                normalized_filters[field_name] = list(default) if multi else default

        for one_config in filters_config:
            base_name = one_config["name"]
            is_multi = one_config["ui_control"] == "multiselect"
            apply(
                base_name,
                [value["v"] for value in one_config["values"]],
                one_config["default"],
                multi=is_multi,
            )
            apply(
                base_name + "min",
                [value["v"] for value in one_config["min_values"]],
                one_config["min_default"],
            )
            apply(
                base_name + "max",
                [value["v"] for value in one_config["max_values"]],
                one_config["max_default"],
            )

        return normalized_filters

    @classmethod
    def _hash(cls, normalized: dict) -> str:
        # sort_keys + compact separators keep the serialization stable across
        # Python versions and dict insertion order.
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _run_query(cls, filters: dict) -> list[dict]:
        window_start = timezone.now() - timedelta(days=filters["window"])

        stream_qs = Stream.objects.filter(
            status=Stream.Status.APPROVED,
            finished_at__gte=window_start,
            language=filters["lang"],
        )

        if filters.get("peakmin") is not None:
            stream_qs = stream_qs.filter(max_viewers__gte=filters["peakmin"])
        if filters.get("peakmax") is not None:
            stream_qs = stream_qs.filter(max_viewers__lte=filters["peakmax"])
        if filters.get("avgmin") is not None:
            stream_qs = stream_qs.filter(avg_viewers__gte=filters["avgmin"])
        if filters.get("avgmax") is not None:
            stream_qs = stream_qs.filter(avg_viewers__lte=filters["avgmax"])
        if filters.get("durmin") is not None:
            stream_qs = stream_qs.filter(duration__gte=filters["durmin"])
        if filters.get("durmax") is not None:
            stream_qs = stream_qs.filter(duration__lte=filters["durmax"])
        if filters.get("genres"):
            genres = filters["genres"]
            stream_qs = stream_qs.filter(genre_ids__overlap=genres if isinstance(genres, list) else [genres])

        stream_qs = stream_qs.annotate(
            finished_dow=ExtractIsoWeekDay("finished_at")
        )
        if filters.get("wdays"):
            stream_qs = stream_qs.filter(finished_dow__in=filters["wdays"])

        # One row per streamer, aggregating only the streams that matched the
        # filters above. Sort key mirrors the displayed metrics: peak viewers,
        # then average viewers, then total watch time.
        top_streamer_aggregates = list(
            stream_qs
            .annotate(
                host_login=F("streamer_profile__host_login"),
                host_display_name=F("streamer_profile__host_display_name"),
            )
            .values(
                login=F("host_login"),
                display_name=F("host_display_name"),
                profile_id=F("streamer_profile_id"),
            )
            .annotate(
                streams_count=Count("id"),
                peak_viewers=Max("max_viewers"),
                avg_viewers=Avg("avg_viewers"),
                total_duration_seconds=Sum("duration"),
                # JSONBAgg (not ArrayAgg) because host_game_ids is itself an array
                # and Postgres rejects array_agg of ragged arrays. The JSON array
                # of arrays is flattened + de-duped per streamer below.
                game_id_lists=JSONBAgg("host_game_ids"),
            )
            .order_by("-peak_viewers", "-avg_viewers", "-total_duration_seconds")[:MAX_RESULTS]
        )

        # Resolve every referenced game name in a single round-trip.
        all_game_ids = {
            one_game_id
            for one_streamer in top_streamer_aggregates
            for one_list in (one_streamer.get("game_id_lists") or [])
            for one_game_id in (one_list or [])
        }
        game_names_map = dict(
            Game.objects.filter(host_game_id__in=all_game_ids)
            .values_list("host_game_id", "host_name")
        )

        for one_streamer in top_streamer_aggregates:
            distinct_game_ids = {
                one_game_id
                for one_list in (one_streamer.pop("game_id_lists", None) or [])
                for one_game_id in (one_list or [])
            }
            one_streamer["games"] = sorted(
                {game_names_map.get(one_game_id, "N/A") for one_game_id in distinct_game_ids}
            )
            one_streamer["total_duration"] = cls._format_duration(
                one_streamer.pop("total_duration_seconds", None) or 0
            )
            one_streamer["avg_viewers"] = int(round(one_streamer["avg_viewers"] or 0))

        return top_streamer_aggregates

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours} h {minutes} min"

    @staticmethod
    @cache
    def get_filters_config() -> tuple[list[dict], list]:
        game_genres = [("any", "Any genre")] + list(GameGenre.objects.values_list("host_genre_id", "host_name"))
        return [
            __class__._filter_defaults(
                ui_control="range",
                name="peak",
                label="Max Viewers",
                min_values=[{"v": "any", "l": "Min"}] + __class__._get_viewers_filter_values(),
                min_default=5,
                max_values=__class__._get_viewers_filter_values() + [{"v": "any", "l": "Max"}],
                max_default=200,
            ),
            __class__._filter_defaults(
                ui_control="range",
                name="avg",
                label="Avg Viewers",
                min_values=[{"v": "any", "l": "Min"}] + __class__._get_viewers_filter_values(),
                min_default=5,
                max_values=__class__._get_viewers_filter_values() + [{"v": "any", "l": "Max"}],
                max_default=200,
            ),
            __class__._filter_defaults(
                ui_control="range",
                name="dur",
                label="Stream Duration",
                min_values=[{"v": "any", "l": "Min"}] + __class__._get_time_filter_values(),
                min_default=7200,
                max_values=__class__._get_time_filter_values() + [{"v": "any", "l": "Max"}],
                max_default="any",
            ),
            __class__._filter_defaults(
                ui_control="dropdown",
                name="window",
                label="Time Window *",
                values=[
                    {"v": 7, "l": "1 Week"},
                    {"v": 14, "l": "2 Weeks"},
                    {"v": 21, "l": "3 Weeks"},
                    {"v": 28, "l": "4 Weeks"},
                ],
                default=14,
            ),
            __class__._filter_defaults(
                ui_control="dropdown",
                name="genres",
                label="Game Genre",
                values=[{"v": str(one_value), "l": one_label} for one_value, one_label in game_genres],
                default="any",
            ),
            __class__._filter_defaults(
                ui_control="dropdown",
                name="lang",
                label="Language",
                values=[
                    {"v": "en", "l": "English"},
                    {"v": "fr", "l": "French"},
                    {"v": "de", "l": "German"}
                ],
                default="en",
            ),
            __class__._filter_defaults(
                ui_control="multiselect",
                name="wdays",
                label="Days of Week *",
                values=[
                    {"v": 1, "l": "Mon"},
                    {"v": 2, "l": "Tue"},
                    {"v": 3, "l": "Wed"},
                    {"v": 4, "l": "Thu"},
                    {"v": 5, "l": "Fri"},
                    {"v": 6, "l": "Sat"},
                    {"v": 7, "l": "Sun"},
                ],
                default=[1, 5, 6, 7],
            ),
        ], ["lang", "window", "peakmin", "peakmax", "avgmin", "avgmax", "durmin", "durmax", "genres", "wdays"]

    @staticmethod
    def _get_viewers_filter_values():
        return [
            {"v": 5, "l": "5"},
            {"v": 10, "l": "10"},
            {"v": 15, "l": "15"},
            {"v": 20, "l": "20"},
            {"v": 30, "l": "30"},
            {"v": 40, "l": "40"},
            {"v": 50, "l": "50"},
            {"v": 75, "l": "75"},
            {"v": 100, "l": "100"},
            {"v": 150, "l": "150"},
            {"v": 200, "l": "200"},
            {"v": 250, "l": "250"},
            {"v": 300, "l": "300"},
            {"v": 400, "l": "400"},
            {"v": 500, "l": "500"},
            {"v": 750, "l": "750"},
            {"v": 1000, "l": "1000"},
            {"v": 2000, "l": "2000"},
            {"v": 3000, "l": "3000"},
            {"v": 4000, "l": "4000"},
            {"v": 5000, "l": "5000"},
        ]

    @staticmethod
    def _get_time_filter_values():
        return [
            {"v": 3600, "l": "1 h"},
            {"v": 7200, "l": "2 h"},
            {"v": 10800, "l": "3 h"},
            {"v": 21600, "l": "6 h"},
            {"v": 32400, "l": "9 h"},
            {"v": 43200, "l": "12 h"},
            {"v": 86400, "l": "24 h"}
        ]

    @staticmethod
    def _filter_defaults(**kwargs) -> dict:
        form_field = {
            "ui_control": "",
            "name": "",
            "label": "",
            "values": [],
            "default": "",
            "min_values": [],
            "min_default": "",
            "max_values": [],
            "max_default": "",
        }
        for key, value in kwargs.items():
            form_field[key] = value
        return form_field
