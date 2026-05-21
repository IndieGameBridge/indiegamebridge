import hashlib
import json
import logging
from datetime import timedelta

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import Max, F
from django.db.models.functions import ExtractIsoWeekDay, JSONObject
from django.utils import timezone

from apps.streams.models import Game, SearchCache, Stream

logger = logging.getLogger(__name__)


SEARCH_CACHE_TTL = timedelta(hours=1)


class StreamerSearch:
    """Single entry point for streamer search.

    Responsibilities:
      - Define the canonical default filters (used by home and `/streamers` default).
      - Normalize incoming filters into a deterministic shape so equivalent
        searches share one cache entry.
      - Read/write the SearchCache with TTL-on-read semantics.
      - Run the underlying aggregation query against `Stream`.
    """

    # Sentinel values the frontend form uses to mean "no constraint".
    _RANGE_OPEN = {"min", "max", "", None}
    _GENRE_ANY = "any"

    @classmethod
    def default_filters(cls) -> dict:
        # Concrete values that produce the demo results currently shown on home.
        # Both home (cached page) and /streamers (no params) should call
        # StreamerSearch(default_filters()).results() so the two surfaces stay
        # in lock-step.
        return {
            "max_viewers_min": 100,
            "max_viewers_max": 100000,
            "duration_min": 1800,
            "duration_max": 36000,
            "language": "en",
            "time_window": 14,
            "genre_ids": [5],
            "week_days": [1, 2, 3, 4, 5, 6, 7],
            "results_n": 10,
        }

    def __init__(self, filters: dict | None = None):
        self.raw_filters = filters or {}
        self.filters = self._normalize(self.raw_filters)
        self.key_hash = self._hash(self.filters)

    def results(self) -> list[dict]:
        now = timezone.now()
        cached = SearchCache.objects.filter(key_hash=self.key_hash).first()

        if cached and (now - cached.refreshed_at) < SEARCH_CACHE_TTL:
            # Hit: touch last_hit_at (used by future eviction) and return as-is.
            SearchCache.objects.filter(pk=cached.pk).update(last_hit_at=now)
            logger.debug("Search cache hit: %s", self.key_hash[:12])
            return cached.results

        # Miss or stale: recompute and upsert. update_or_create resolves the
        # race between two concurrent first-misses into a single row.
        logger.debug(
            "Search cache %s: %s",
            "stale" if cached else "miss",
            self.key_hash[:12],
        )
        fresh = self._run_query(self.filters)
        SearchCache.objects.update_or_create(
            key_hash=self.key_hash,
            defaults={
                "filters": self.filters,
                "results": fresh,
                "last_hit_at": now,
            },
        )
        return fresh

    @classmethod
    def _normalize(cls, raw: dict) -> dict:
        # Start from defaults so any key the caller omitted has a value, then
        # overlay caller-provided values after coercion. Sentinels resolve to
        # None for unbounded — the query skips clauses for None values, and
        # the hash treats them as a single canonical "no constraint".
        out = dict(cls.default_filters())

        for name in ("max_viewers", "duration"):
            if f"{name}_min" in raw:
                out[f"{name}_min"] = cls._coerce_int(raw[f"{name}_min"])
            if f"{name}_max" in raw:
                out[f"{name}_max"] = cls._coerce_int(raw[f"{name}_max"])

        if "language" in raw:
            out["language"] = (raw["language"] or "").strip().lower() or out["language"]

        if "time_window" in raw:
            out["time_window"] = cls._coerce_int(raw["time_window"]) or out["time_window"]

        if "genre_ids" in raw or "genre" in raw:
            value = raw.get("genre_ids", raw.get("genre"))
            out["genre_ids"] = cls._coerce_genre_list(value)

        if "week_days" in raw:
            out["week_days"] = cls._coerce_week_days(raw["week_days"])

        if "results_n" in raw:
            # Cap to keep one request from materializing a huge payload.
            out["results_n"] = max(1, min(cls._coerce_int(raw["results_n"]) or out["results_n"], 50))

        return out

    @classmethod
    def _coerce_int(cls, value) -> int | None:
        if value in cls._RANGE_OPEN:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _coerce_genre_list(cls, value) -> list[int]:
        # "any" or any "any" inside a list → unbounded → empty list.
        if value is None or value == cls._GENRE_ANY:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return []
        if cls._GENRE_ANY in value:
            return []
        cleaned = []
        for one in value:
            try:
                cleaned.append(int(one))
            except (TypeError, ValueError):
                continue
        return sorted(set(cleaned))

    @classmethod
    def _coerce_week_days(cls, value) -> list[int]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return []
        cleaned = []
        for one in value:
            try:
                one_int = int(one)
            except (TypeError, ValueError):
                continue
            if 1 <= one_int <= 7:
                cleaned.append(one_int)
        return sorted(set(cleaned))

    @classmethod
    def _hash(cls, normalized: dict) -> str:
        # sort_keys + compact separators keep the serialization stable across
        # Python versions and dict insertion orders.
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _run_query(cls, filters: dict) -> list[dict]:
        window_start = timezone.now() - timedelta(days=filters["time_window"])

        stream_qs = Stream.objects.filter(
            status=Stream.Status.APPROVED,
            finished_at__gte=window_start,
            language=filters["language"],
        )

        if filters.get("max_viewers_min") is not None:
            stream_qs = stream_qs.filter(max_viewers__gte=filters["max_viewers_min"])
        if filters.get("max_viewers_max") is not None:
            stream_qs = stream_qs.filter(max_viewers__lte=filters["max_viewers_max"])
        if filters.get("duration_min") is not None:
            stream_qs = stream_qs.filter(duration__gte=filters["duration_min"])
        if filters.get("duration_max") is not None:
            stream_qs = stream_qs.filter(duration__lte=filters["duration_max"])
        if filters.get("genre_ids"):
            stream_qs = stream_qs.filter(genre_ids__overlap=filters["genre_ids"])

        stream_qs = stream_qs.annotate(
            finished_dow=ExtractIsoWeekDay("finished_at")
        )
        if filters.get("week_days"):
            stream_qs = stream_qs.filter(finished_dow__in=filters["week_days"])

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
                peak_viewers=Max("max_viewers"),
                streams=JSONBAgg(
                    JSONObject(
                        id="id",
                        duration="duration",
                        max_viewers="max_viewers",
                        language="language",
                        game_ids="host_game_ids",
                        started_at="started_at",
                        finished_at="finished_at",
                    )
                ),
            )
            .order_by("-peak_viewers")[: filters["results_n"]]
        )

        # Resolve every referenced game in a single round-trip.
        all_game_ids = {
            one_game_id
            for one_streamer in top_streamer_aggregates
            for one_stream in one_streamer.get("streams", [])
            for one_game_id in (one_stream.get("game_ids") or [])
        }
        game_names_map = dict(
            Game.objects.filter(host_game_id__in=all_game_ids)
            .values_list("host_game_id", "host_name")
        )

        for one_streamer in top_streamer_aggregates:
            for one_stream in one_streamer.get("streams", []):
                one_stream["games"] = [
                    game_names_map.get(game_id, "N/A")
                    for game_id in (one_stream.get("game_ids") or [])
                ]
                one_stream["duration"] = cls._format_duration(one_stream["duration"])
                one_stream.pop("game_ids", None)

        return top_streamer_aggregates

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours} h {minutes} min"
