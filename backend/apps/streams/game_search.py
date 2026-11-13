import unicodedata
from functools import cache

from django.db.models import Count, Exists, OuterRef, Q
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

# The name box's param, how much of what's typed is read, and how many of its words.
NAME_FILTER = "name"
NAME_MAX_LENGTH = 100
NAME_MAX_WORDS = 10


def _letter_variants() -> dict[str, str]:
    """Each plain letter with the accented Latin letters that fold to it, in either case:
    e with éÉèÈ and the rest, o with öÖ, ōŌ and the rest. The straight apostrophe gets the
    two curly ones. Twitch spells Pokémon with its é and Don’t with a curly apostrophe, but
    people type pokemon and don't."""
    variants = {"'": chr(0x2018) + chr(0x2019)}
    for code in range(0xC0, 0x180):
        letter = chr(code)
        base = "".join(part for part in unicodedata.normalize("NFD", letter) if not unicodedata.combining(part))
        if base != letter and len(base) == 1 and base.isascii():
            variants[base.lower()] = variants.get(base.lower(), "") + letter
    return variants


LETTER_VARIANTS = _letter_variants()
FOLD = str.maketrans({variant: plain for plain, variants in LETTER_VARIANTS.items() for variant in variants})


def _fold(text: str) -> str:
    """What's typed, plain and lower case: Pokémon to pokemon. Composed first, so an accent
    typed as a separate mark folds too."""
    return unicodedata.normalize("NFC", text).translate(FOLD).lower()


def _word_pattern(word: str) -> str:
    """A folded word as a pattern for Postgres's case-insensitive regex match, so it finds
    the name as stored: pokemon becomes p[oöō…]k[eéè…]m[oöō…][nñń…], which matches Pokémon
    Go. Folding every name in SQL instead cost 20 times as much."""
    parts = []
    for char in word:
        if char in LETTER_VARIANTS:
            parts.append(f"[{char}{LETTER_VARIANTS[char]}]")
        elif char.isascii() and not char.isalnum():
            # A pattern's operators are all ASCII punctuation, and a backslash makes each one
            # literal: the dots of R.E.P.O. stay dots, and ( or [ can't break the pattern.
            parts.append("\\" + char)
        else:
            # Letters, digits and anything beyond ASCII read as themselves.
            parts.append(char)
    return "".join(parts)


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
                "game_id", "game__host_name", "game__release_date", "position", "hours__0_3", "streams__0_3",
            )[offset:offset + limit]
        )
        newest_hour = self.newest_hour()
        genres = self._genre_names([row["game_id"] for row in rows])
        places = self._places([row["position"] for row in rows], offset)
        results = []
        for row, place in zip(rows, places):
            release_date = row["game__release_date"]
            # The arrays run newest first, so the newest hours' numbers are in their first cells.
            streams_by_hour = dict(zip(row["hours__0_3"], row["streams__0_3"]))
            results.append({
                "id": row["game_id"],
                "place": place,
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

    def _places(self, positions: list[int], offset: int) -> list[int]:
        """Each row's number: its place in the list the other filters make. So a game found
        by its name keeps the number it has there, and shows where it stands: #98, not #1."""
        if NAME_FILTER not in self.filters:
            return list(range(offset + 1, offset + len(positions) + 1))
        if not positions or not any(name in self.filters for name in (*GENRE_FILTER_NAMES, "year")):
            # The language's and size's whole list: the place is the stored one.
            return positions
        # Genres or a year make a shorter list, so count the games ahead of each row in it,
        # all of the page's rows in one pass down to the last of them.
        ahead = (
            self._queryset(by_name=False)
            .filter(position__lt=positions[-1])
            .aggregate(**{
                f"ahead_{index}": Count("pk", filter=Q(position__lt=position))
                for index, position in enumerate(positions)
            })
        )
        return [ahead[f"ahead_{index}"] + 1 for index in range(len(positions))]

    def _queryset(self, by_name: bool = True):
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
        if by_name and NAME_FILTER in self.filters:
            # Every word typed, anywhere in the name and in any order: "knight hollow" finds
            # Hollow Knight: Silksong.
            for word in self._name_words():
                qs = qs.filter(game__host_name__iregex=_word_pattern(word))
        return qs.order_by("position")

    def _name_words(self) -> list[str]:
        # Each word once, and only so many: each one is another match on every name.
        return list(dict.fromkeys(_fold(self.filters[NAME_FILTER]).split()))[:NAME_MAX_WORDS]

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
            if one_filter["name"] == NAME_FILTER:
                continue
            allowed = {str(value["v"]): value["v"] for value in one_filter["values"]}
            value = allowed.get(str(raw.get(one_filter["name"])), one_filter["default"])
            if value != "any":
                filters[one_filter["name"]] = value
        # The name box takes any text, as printable characters only (Postgres refuses a NUL),
        # its spaces collapsed and cut to the box's length. Left empty, it's no filter.
        typed = "".join(char if char.isprintable() else " " for char in str(raw.get(NAME_FILTER) or ""))
        name = " ".join(typed.split())[:NAME_MAX_LENGTH].strip()
        if name:
            filters[NAME_FILTER] = name
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
            # A text box rather than a dropdown, so it has no values to pick from.
            {
                "name": NAME_FILTER,
                "label": "Game Name",
                "type": "text",
                "placeholder": "Any game",
                "max_length": NAME_MAX_LENGTH,
                "values": [],
                "default": "",
            },
        ]
