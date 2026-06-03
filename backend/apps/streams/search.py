import logging
from functools import cache

from apps.streams.models import GameGenre, StreamerSearchStats

logger = logging.getLogger(__name__)


# Hard cap on how many results a search pages through; the API slices this into
# pages of PAGE_SIZE.
MAX_RESULTS = 1000
PAGE_SIZE = 50


class StreamerSearch:
    """Single entry point for streamer search.

    Reads the precomputed StreamerSearchStats read-model (rebuilt out of band by
    the rebuild_search_stats command), so a search is just a filter + sort over a
    small per-(streamer, language) table - never a scan of the wide streams
    table. The stats are roughly a day stale by design.
    """

    def __init__(self, filters: dict | None = None):
        self.raw_filters = filters or {}
        self.filters = self._normalize_query_params(self.raw_filters)
        self._queryset = None

    def results(self, offset: int = 0, limit: int = PAGE_SIZE) -> list[dict]:
        rows = list(
            self._stats_queryset().values(
                "streamer_profile_id",
                "host_login",
                "host_display_name",
                "peak_viewers",
                "avg_viewers",
                "total_duration_seconds",
                "streams_count",
                "genre_ids",
            )[offset:offset + limit]
        )

        genre_names = self._genre_name_map()
        for row in rows:
            row["profile_id"] = row.pop("streamer_profile_id")
            row["login"] = row.pop("host_login")
            row["display_name"] = row.pop("host_display_name")
            # Display value: "X hours in last 4 weeks".
            row["hours_streamed"] = (row.pop("total_duration_seconds") or 0) // 3600
            row["genres"] = sorted(
                genre_names.get(genre_id, "N/A") for genre_id in (row.pop("genre_ids") or [])
            )
        return rows

    def total(self) -> int:
        # Capped to MAX_RESULTS to match the pageable result set.
        return min(self._stats_queryset().count(), MAX_RESULTS)

    def _stats_queryset(self):
        if self._queryset is not None:
            return self._queryset

        qs = StreamerSearchStats.objects.filter(language=self.filters["lang"])
        if self.filters.get("peakmin") is not None:
            qs = qs.filter(peak_viewers__gte=self.filters["peakmin"])
        if self.filters.get("peakmax") is not None:
            qs = qs.filter(peak_viewers__lte=self.filters["peakmax"])
        if self.filters.get("avgmin") is not None:
            qs = qs.filter(avg_viewers__gte=self.filters["avgmin"])
        if self.filters.get("avgmax") is not None:
            qs = qs.filter(avg_viewers__lte=self.filters["avgmax"])
        if self.filters.get("genres"):
            genres = self.filters["genres"]
            qs = qs.filter(genre_ids__overlap=genres if isinstance(genres, list) else [genres])

        # Matches the language-leading index, so this is an index-ordered scan.
        self._queryset = qs.order_by("-peak_viewers", "-avg_viewers", "-total_duration_seconds")
        return self._queryset

    @staticmethod
    @cache
    def _genre_name_map() -> dict:
        return dict(GameGenre.objects.values_list("host_genre_id", "host_name"))

    @classmethod
    def _normalize_query_params(cls, raw: dict) -> dict:
        normalized_filters = {}
        filters_config, allowed_names = cls.get_filters_config()

        # Trust only configuration names and values. "any" sentinels are dropped
        # from the normalized dict so equivalent "no-filter" requests look the
        # same and _stats_queryset can use simple `key in filters` checks. Raw
        # values arrive as strings from request.GET but allowed_values are typed
        # (e.g. int 100, not "100"), so we resolve by string-equality and return
        # the typed counterpart.
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
                ui_control="dropdown",
                name="genres",
                label="Game Genre",
                # int genre ids (matching the stored genre_ids array); "any" drops the filter.
                values=[{"v": one_value, "l": one_label} for one_value, one_label in game_genres],
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
        ], ["lang", "peakmin", "peakmax", "avgmin", "avgmax", "genres"]

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
