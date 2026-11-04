from functools import cache

from django.db.models import Exists, OuterRef
from django.db.models.functions import ExtractYear

from apps.streams.languages import ALL_LANGUAGES, LANGUAGE_NAMES, PAGE_LANGUAGES
from apps.streams.management.commands.rebuild_game_stats import GAME_STATS_CACHE_KEY, WINDOW_HOURS
from apps.streams.models import Game, GameGenre, GameStats, JsonCache
from apps.streams.search import GENRE_FILTER_NAMES
from apps.streams.size_groups import SIZE_FILTER_VALUES, SIZE_GROUPS

PAGE_SIZE = 50

# How many of the newest hours a result row shows.
RECENT_HOURS = 3

# The stored number of each size filter value. "any" is dropped from a search's filters, as
# in the streamer search, so it's the fallback rather than a key here.
SIZE_GROUP_NUMBERS = {group.label: number for number, group in enumerate(SIZE_GROUPS, 1)}

# Params that page the results rather than filter them.
PAGING_PARAMS = ("p",)


class GameSearch:
    """Single entry point for the Games page's search.

    Reads the precomputed GameStats read model, rebuilt out of band by rebuild_game_stats:
    a list's order is stored, so a search is a walk down one list and never compares hours.
    The stats are up to 6 hours old by design.
    """

    def __init__(self, filters: dict | None = None):
        self.filters = self._normalize(filters or {})

    @classmethod
    def from_query_params(cls, query_params) -> "GameSearch":
        return cls({key: query_params.get(key) for key in query_params.keys() if key not in PAGING_PARAMS})

    def results(self, offset: int = 0, limit: int = PAGE_SIZE) -> list[dict]:
        rows = list(
            self._queryset().values(
                "game_id", "game__host_name", "game__release_date", "hours__0_3", "streams__0_3",
            )[offset:offset + limit]
        )
        newest_hour = self.newest_hour()
        genres = self._genre_names([row["game_id"] for row in rows])
        results = []
        for row in rows:
            release_date = row["game__release_date"]
            # The arrays run newest first, so the newest hours' numbers are in their first cells.
            streams_by_hour = dict(zip(row["hours__0_3"], row["streams__0_3"]))
            results.append({
                "id": row["game_id"],
                "name": row["game__host_name"],
                "release_year": release_date.year if release_date else None,
                "genres": genres.get(row["game_id"], []),
                "recent_streams": [
                    streams_by_hour.get(newest_hour - age, 0) for age in range(RECENT_HOURS)
                ] if newest_hour is not None else [],
            })
        return results

    def total(self) -> int:
        return self._queryset().count()

    @staticmethod
    def newest_hour() -> int | None:
        """The newest hour the stats hold, as whole hours since the Unix epoch; None until
        rebuild_game_stats has first run."""
        cached = JsonCache.objects.filter(key=GAME_STATS_CACHE_KEY).first()
        return cached.content["newest_hour"] if cached else None

    @classmethod
    def hours_of_game(cls, game_id: int, size: str | None) -> dict:
        """One game's chart: every page language's hours for one size filter value."""
        size_group = SIZE_GROUP_NUMBERS.get(size, GameStats.ANY_SIZE)
        lines = (
            GameStats.objects
            .filter(game_id=game_id, size_group=size_group)
            .exclude(language=ALL_LANGUAGES)
            .values_list("language", "hours", "streams")
        )
        return {
            "newest_hour": cls.newest_hour(),
            "window_hours": WINDOW_HOURS,
            "lines": {language: {"hours": hours, "streams": streams} for language, hours, streams in lines},
        }

    def _queryset(self):
        qs = GameStats.objects.filter(
            language=self.filters["lang"],
            size_group=SIZE_GROUP_NUMBERS.get(self.filters.get("peak"), GameStats.ANY_SIZE),
        )
        # The genre dropdowns are ANDed, as in the streamer search: a game qualifies only if
        # it has every genre picked, so each added genre narrows the results.
        links = Game.genres.through.objects
        for name in GENRE_FILTER_NAMES:
            if name in self.filters:
                qs = qs.filter(Exists(links.filter(
                    game_id=OuterRef("game_id"), gamegenre__host_genre_id=self.filters[name],
                )))
        if "year" in self.filters:
            qs = qs.filter(game__release_date__year=self.filters["year"])
        return qs.order_by("position")

    @staticmethod
    def _genre_names(game_ids: list[int]) -> dict[int, list[str]]:
        names = {}
        rows = (
            Game.genres.through.objects
            .filter(game_id__in=game_ids)
            .order_by("gamegenre__host_name")
            .values_list("game_id", "gamegenre__host_name")
        )
        for game_id, name in rows:
            names.setdefault(game_id, []).append(name)
        return names

    @classmethod
    def _normalize(cls, raw: dict) -> dict:
        # Trust only the form's values, matched as text since a query string's are. What's
        # set to "any" is left out, so _queryset can check for a filter by its name.
        filters = {}
        for one_filter in cls.get_filters_config():
            allowed = {str(value["v"]): value["v"] for value in one_filter["values"]}
            value = allowed.get(str(raw.get(one_filter["name"])), one_filter["default"])
            if value != "any":
                filters[one_filter["name"]] = value
        return filters

    @staticmethod
    @cache
    def get_filters_config() -> list[dict]:
        game_genres = list(GameGenre.objects.order_by("host_name").values_list("host_genre_id", "host_name"))

        def genre_filter(name: str, label: str, empty_label: str) -> dict:
            return {
                "name": name,
                "label": label,
                "values": [{"v": "any", "l": empty_label}] + [{"v": value, "l": text} for value, text in game_genres],
                "default": "any",
            }

        years = (
            Game.objects
            .filter(category=Game.Category.ISGAME, release_date__isnull=False)
            .annotate(year=ExtractYear("release_date"))
            .order_by("-year")
            .values_list("year", flat=True)
            .distinct()
        )
        return [
            {
                "name": "lang",
                "label": "Language",
                "values": [{"v": ALL_LANGUAGES, "l": "All languages"}]
                    + [{"v": code, "l": LANGUAGE_NAMES[code]} for code in PAGE_LANGUAGES],
                "default": ALL_LANGUAGES,
            },
            {
                "name": "peak",
                "label": "Max Viewers",
                "values": SIZE_FILTER_VALUES,
                "default": "any",
            },
            genre_filter(GENRE_FILTER_NAMES[0], "Game Genre #1", "Any genre"),
            genre_filter(GENRE_FILTER_NAMES[1], "Game Genre #2", "None"),
            genre_filter(GENRE_FILTER_NAMES[2], "Game Genre #3", "None"),
            {
                "name": "year",
                "label": "Release Year",
                "values": [{"v": "any", "l": "Any year"}] + [{"v": year, "l": str(year)} for year in years],
                "default": "any",
            },
        ]
