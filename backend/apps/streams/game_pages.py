"""The per-game public pages, /game/<slug>: which games get one, their addresses, and what a
page says. rebuild_game_pages computes each page's numbers into its GamePage row every 6 hours;
page_content() turns a row into the page the API serves, with the game's past months from
GameMonthStats, which archive_streams counts once a month.

A page compares its game with a baseline: indie games for a game IGDB lists in the Indie genre,
every game for the rest.
"""

from calendar import monthrange
from datetime import date
from urllib.parse import urlencode

from django.db.models import Count
from django.utils.text import slugify

from apps.streams.languages import ALL_LANGUAGES, COLLECTED_SINCE, LANGUAGE_NAMES, PAGE_LANGUAGES, day_month_year, names_of
from apps.streams.models import ArchivedMonth, GameMonthStats, GamePage, JsonCache
from apps.streams.size_groups import PEAK_THRESHOLDS, SIZE_GROUPS

# A game gets a page the first time this many different streamers played it in 4 weeks.
PAGE_MIN_STREAMERS = 10
# From this many streamers in the 4 weeks, a page shows more than totals: below it, a public page
# could describe one or two people's habits. Search engines may index every page, whatever its
# numbers: a page once in their results stays there, rather than leaving as its game goes quiet
# and coming back when it's streamed again.
DETAIL_MIN_STREAMERS = 5

# "Streamers who played it also played": up to ALSO_PLAYED_COUNT games, each played by at least
# ALSO_PLAYED_MIN_SHARED of its streamers and at least ALSO_PLAYED_MIN_LIFT times as often as by
# streamers in general. Ranked by that ratio, weighed down below ALSO_PLAYED_FULL_WEIGHT shared
# streamers, so 7 streamers at 94 times don't push out 266 at 33 times.
ALSO_PLAYED_COUNT = 3
ALSO_PLAYED_MIN_SHARED = 5
ALSO_PLAYED_MIN_LIFT = 3
ALSO_PLAYED_FULL_WEIGHT = 20

# The trend compares the newest week's streamers with the oldest week's, from this many then.
TREND_MIN_STREAMERS = 30
# A share of small streamers this many points from the baseline's is worth saying.
SIZE_GAP_POINTS = 10
# A language stands out at this many times its baseline share, once it holds this share of the
# game's streams; from FAVOURITE_SHARE, it's the game's favourite.
LANGUAGE_RATIO = 1.3
LANGUAGE_MIN_SHARE = 0.05
FAVOURITE_SHARE = 0.5
# The languages bars name this many, and add the rest up.
LANGUAGE_BARS = 4
# The busiest and quietest hours, in windows of this many hours.
HOURS_WINDOW = 3

# IGDB's Indie genre: its games are compared with indie games, the others with every game.
INDIE_GENRE_ID = 32

# Where rebuild_game_pages keeps the baselines: the sizes and languages of indie games and of
# every game.
BASELINES_CACHE_KEY = "game_page_baselines"

# How the page names its baseline: in "against 64% for indie games", and in "typical for an
# indie game".
BASELINE_NAMES = {
    "indie": {"plural": "indie games", "one": "an indie game"},
    "all": {"plural": "games on Twitch", "one": "a game on Twitch"},
}

# The weeks' names, newest first, as the row's numbers hold them and as the page shows them, like
# the months below them.
WEEK_LABELS = ("Last week", "2 weeks ago", "3 weeks ago", "4 weeks ago")

# The month by month history says a month "more than doubled" from this many times the month
# before, once that month had JUMP_MIN_STREAMERS; a game "held steady" while every month stayed
# within STEADY_RATIO of each other, each with STEADY_MIN_STREAMERS, over STEADY_MIN_MONTHS.
JUMP_RATIO = 2
JUMP_MIN_STREAMERS = 20
STEADY_RATIO = 1.5
STEADY_MIN_STREAMERS = 30
STEADY_MIN_MONTHS = 3
# A language's streams "drew more viewers" from this many times the average of the language
# most of its streamers streamed it in.
VIEWERS_RATIO = 2
# What a hidden number shows, and says on hover.
HIDDEN = "–"
HIDDEN_HINT = "1 to 4 streamers: only their totals are shown."


def slug_base(name: str) -> str:
    """A name as an address: "Hollow Knight: Silksong" to hollow-knight-silksong, Pokémon to
    pokemon. Empty for a name with no Latin letters or digits, such as a Japanese one."""
    return slugify(name)[:200].strip("-")


def new_slug(name: str, release_year: int | None, host_game_id: int, taken: set[str]) -> str:
    """A new page's address: the name; on a clash, the name and the release year; then the name
    and the game's Twitch id. Three games called Resident Evil 4 get resident-evil-4,
    resident-evil-4-2005 and so on. A name with no Latin letters takes the id alone."""
    base = slug_base(name)
    candidates = [base, f"{base}-{release_year}" if release_year else None, f"{base}-{host_game_id}"] if base else []
    candidates.append(str(host_game_id))
    for candidate in candidates:
        if candidate and candidate not in taken:
            return candidate
    number = 2
    while f"{candidates[-1]}-{number}" in taken:
        number += 1
    return f"{candidates[-1]}-{number}"


def shared_names() -> set[str]:
    """The names that games with pages share: Resident Evil 4, for three games."""
    return set(
        GamePage.objects.values("game__host_name").annotate(pages=Count("id")).filter(pages__gt=1)
        .values_list("game__host_name", flat=True)
    )


def display_name(name: str, release_date, clashes: bool) -> str:
    """A game's name as pages show it: with its release year when another page's game has the
    same name, as in Resident Evil 4 (2005)."""
    return f"{name} ({release_date.year})" if clashes and release_date else name


def baselines() -> dict | None:
    cached = JsonCache.objects.filter(key=BASELINES_CACHE_KEY).first()
    return cached.content if cached else None


def _plural(count: int, one: str, many: str) -> str:
    return f"{count:,} {one if count == 1 else many}"


def _about_hours(hours: int) -> str:
    """Hours as the text rounds them: 19,947 to 19,900, 1,234 to 1,230, 87 stays."""
    if hours >= 10_000:
        hours = round(hours, -2)
    elif hours >= 1_000:
        hours = round(hours, -1)
    return f"{hours:,}"


def _percent(share: float) -> str:
    return "<1%" if 0 < share < 0.005 else f"{round(share * 100)}%"


def _shares(counts: list[int] | dict) -> list[float] | dict:
    values = counts.values() if isinstance(counts, dict) else counts
    total = sum(values)
    if isinstance(counts, dict):
        return {key: (value / total if total else 0.0) for key, value in counts.items()}
    return [value / total if total else 0.0 for value in counts]


def _clock(hour: int) -> str:
    return f"{hour % 24:02d}:00"


def _window(hours_of_day: list[int], busiest: bool) -> int:
    """Where the busiest (or quietest) HOURS_WINDOW hours of the day start, wrapping past
    midnight; the earliest one wins a tie."""
    sums = [sum(hours_of_day[(start + step) % 24] for step in range(HOURS_WINDOW)) for start in range(24)]
    best = max(sums) if busiest else min(sums)
    return sums.index(best)


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


class GamePageContent:
    """One game's page, as the API serves it: its text, numbers and links. Details only from
    DETAIL_MIN_STREAMERS streamers; below that, the totals."""

    def __init__(self, page: GamePage, baselines: dict | None, genres: list[str]):
        self.page = page
        self.game = page.game
        self.numbers = page.numbers or {}
        self.details = page.streamers >= DETAIL_MIN_STREAMERS
        self.genres = genres
        self.group = "indie" if "Indie" in genres else "all"
        self.baseline = (baselines or {}).get(self.group)
        # As rebuild_game_pages names it, with a year where names clash; the game's own name
        # until it first has.
        self.display_name = page.name or self.game.host_name

    def payload(self) -> dict:
        name = self.display_name
        streamers = self.page.streamers
        year = self.game.release_date.year if self.game.release_date else None
        info = " · ".join(part for part in (", ".join(self.genres), f"released {year}" if year else "") if part)
        content = {
            "slug": self.page.slug,
            "name": name,
            "title": f"{name} on Twitch",
            "description": "Who streamed it in the last 4 weeks, in which languages, and at which hours."
                if self.details else "How much it was streamed on Twitch in the last 4 weeks.",
            "info": info or None,
            "breadcrumb": {"label": "Games", "href": "/games"},
            "seo_title": f"{name} on Twitch: Who Streams It | IndieGameBridge",
            "seo_description": self._seo_description(),
            "summary": {"title": "What the numbers say", "paragraphs": self._paragraphs()},
            "tiles": self._tiles(),
            "sizes": None,
            "languages": None,
            "hours_of_day": None,
            "weeks": None,
            "also_played": None,
            "cta": None,
            "notes": self._notes(),
        }
        if self.details:
            content.update({
                "sizes": self._sizes(),
                "languages": self._languages(),
                "hours_of_day": self._hours_of_day(),
                "weeks": self._weeks(),
                "also_played": self._also_played(),
                "cta": self._cta(streamers),
            })
        return content

    # The text.

    def _seo_description(self) -> str:
        name = self.display_name
        if self.page.streamers == 0:
            last = self.page.last_streamed_at
            return f"Nobody streamed {name} on Twitch in the last 4 weeks." + (
                f" It was last streamed on {day_month_year(last.date())}." if last else ""
            )
        if not self.details:
            return f"How many streamers played {name} on Twitch in the last 4 weeks."
        return (
            f"{self.page.streamers:,} streamers played {name} on Twitch in the last 4 weeks. See their sizes, their"
            " languages, the hours it's streamed and the games they also played."
        )

    def _paragraphs(self) -> list[str]:
        name = self.display_name
        streamers = self.page.streamers
        if streamers == 0:
            last = self.page.last_streamed_at
            return [
                f"Nobody streamed {name} on Twitch in the last 4 weeks."
                + (f" It was last streamed on {day_month_year(last.date())}." if last else "")
            ]
        streams = self.numbers.get("streams", 0)
        hours = self.numbers.get("hours", 0)
        first = (
            f"{_plural(streamers, 'streamer', 'streamers')} played {name} on Twitch in the last 4 weeks, in"
            f" {_plural(streams, 'stream', 'streams')}"
            + (f" and about {_about_hours(hours)} hours of play." if hours else ".")
        )
        if not self.details:
            return [first + " Too few streamers played it lately to say more."]
        second = " ".join(filter(None, [self._trend_sentence(), self._sizes_sentence()]))
        third = " ".join(filter(None, [self._language_sentence(), self._hours_sentence(), self._also_played_sentence()]))
        return [paragraph for paragraph in (first, second, third) if paragraph]

    def _trend_sentence(self) -> str | None:
        weeks = self.numbers.get("weeks")
        if not weeks:
            return None
        newest, oldest = weeks[0], weeks[3]
        if oldest < TREND_MIN_STREAMERS:
            return f"About {_plural(round(sum(weeks) / 4), 'streamer', 'streamers')} a week played it."
        ratio = newest / oldest
        if ratio <= 0.7:
            word = "fading"
        elif ratio < 0.9:
            word = "easing"
        elif ratio <= 1.1:
            word = "steady"
        elif ratio < 1.3:
            word = "rising"
        else:
            word = "growing fast"
        return f"Interest is {word}: {newest:,} streamers played it in the last week, against {oldest:,} three weeks earlier."

    def _small_shares(self) -> tuple[float, float] | None:
        """The game's and its baseline's share of streamers in the smallest size group."""
        sizes = self.numbers.get("sizes")
        if not sizes or not sum(sizes) or not self.baseline or not sum(self.baseline["sizes"]):
            return None
        return _shares(sizes)[0], _shares(self.baseline["sizes"])[0]

    def _sizes_sentence(self) -> str | None:
        shares = self._small_shares()
        if shares is None:
            return None
        game_share, base_share = shares
        names = BASELINE_NAMES[self.group]
        peak = f"peak at {PEAK_THRESHOLDS[0]} viewers or fewer"
        gap = (game_share - base_share) * 100
        if gap >= SIZE_GAP_POINTS:
            return (
                f"It's a small streamers' game: {_percent(game_share)} of its streamers {peak}, against"
                f" {_percent(base_share)} for {names['plural']}."
            )
        if gap <= -SIZE_GAP_POINTS:
            return (
                f"It draws bigger channels than most {names['plural']}: {_percent(game_share)} of its streamers"
                f" {peak}, against {_percent(base_share)}."
            )
        return (
            f"Its streamers' sizes are typical for {names['one']}: {_percent(game_share)} of them {peak}, against"
            f" {_percent(base_share)} for {names['plural']} overall."
        )

    def _language_shares(self) -> tuple[dict, dict] | None:
        languages = self.numbers.get("languages")
        if not languages or not self.baseline:
            return None
        game = _shares({code: one["streams"] for code, one in languages.items()})
        base = _shares(self.baseline["languages"])
        return game, base

    def _language_sentence(self) -> str | None:
        shares = self._language_shares()
        if shares is None:
            return None
        game, base = shares
        names = BASELINE_NAMES[self.group]
        standouts = [
            (game[code] - base.get(code, 0), code) for code in game
            if game[code] >= LANGUAGE_MIN_SHARE and base.get(code) and game[code] >= LANGUAGE_RATIO * base[code]
        ]
        if standouts:
            _, code = max(standouts)
            label = LANGUAGE_NAMES[code]
            if game[code] >= FAVOURITE_SHARE and code != "en":
                return (
                    f"It's a {label} favourite: {_percent(game[code])} of its streams are in {label}, against"
                    f" {_percent(base[code])} for {names['plural']}."
                )
            return (
                f"It's streamed in {label} more than {names['plural']} usually are: {_percent(game[code])} of its"
                f" streams, against {_percent(base[code])}."
            )
        code = max(game, key=game.get)
        return (
            f"Its languages are close to those of {names['plural']}: {_percent(game[code])} of its streams are in"
            f" {LANGUAGE_NAMES[code]}, against {_percent(base.get(code, 0))}."
        )

    def _hours_sentence(self) -> str | None:
        hours_of_day = self.numbers.get("hours_of_day")
        if not hours_of_day or not sum(hours_of_day):
            return None
        busiest, quietest = _window(hours_of_day, True), _window(hours_of_day, False)
        return (
            f"It's streamed most between {_clock(busiest)} and {_clock(busiest + HOURS_WINDOW)} UTC, and least between"
            f" {_clock(quietest)} and {_clock(quietest + HOURS_WINDOW)} UTC."
        )

    def _also_played_sentence(self) -> str | None:
        games = self.numbers.get("also_played")
        if not games:
            return None
        return f"Streamers who played it also often played {_names([game['name'] for game in games])}."

    # The sections.

    def _tiles(self) -> list[dict]:
        # Nobody streamed it lately: the text says so, and three zeros would add nothing.
        if self.page.streamers == 0:
            return []
        tiles = [
            {"label": "Streamers", "value": f"{self.page.streamers:,}"},
            {"label": "Streams", "value": f"{self.numbers.get('streams', 0):,}"},
            {"label": "Hours played", "value": _about_hours(self.numbers.get("hours", 0))},
        ]
        if self.details:
            tiles.append({"label": "Languages", "value": f"{len(self.numbers.get('languages') or {}):,}"})
        return tiles

    def _baseline_caption(self) -> str:
        return f"The dark tick is the share for {BASELINE_NAMES[self.group]['plural']}." if self.baseline else ""

    def _sizes(self) -> dict | None:
        sizes = self.numbers.get("sizes")
        if not sizes or not sum(sizes):
            return None
        game = _shares(sizes)
        base = _shares(self.baseline["sizes"]) if self.baseline else None
        return {
            "title": "Streamer sizes",
            "caption": " ".join(filter(None, [
                "By each streamer's highest viewer count in the last 4 weeks.", self._baseline_caption(),
            ])),
            "bars": [
                {
                    "label": group.label,
                    "share": game[index],
                    "value": _percent(game[index]),
                    "baseline": base[index] if base else None,
                }
                for index, group in enumerate(SIZE_GROUPS)
            ],
        }

    def _languages(self) -> dict | None:
        shares = self._language_shares()
        languages = self.numbers.get("languages")
        if not languages:
            return None
        game, base = shares if shares else (_shares({code: one["streams"] for code, one in languages.items()}), None)
        ordered = sorted(game, key=lambda code: (-game[code], PAGE_LANGUAGES.index(code)))
        # All of them when one more bar would do; otherwise the first few and the rest added up.
        named = ordered if len(ordered) <= LANGUAGE_BARS + 1 else ordered[:LANGUAGE_BARS]
        bars = [
            {
                "label": LANGUAGE_NAMES[code],
                "share": game[code],
                "value": _percent(game[code]),
                "baseline": base.get(code, 0) if base else None,
            }
            for code in named
        ]
        rest = ordered[len(named):]
        if rest:
            share = sum(game[code] for code in rest)
            bars.append({"label": f"{len(rest)} others", "share": share, "value": _percent(share), "baseline": None})
        return {
            "title": "Languages",
            "caption": " ".join(filter(None, [
                "Share of its streams in each broadcast language.", self._baseline_caption(),
            ])),
            "bars": bars,
        }

    def _hours_of_day(self) -> dict | None:
        hours_of_day = self.numbers.get("hours_of_day")
        if not hours_of_day or not sum(hours_of_day):
            return None
        busiest, quietest = _window(hours_of_day, True), _window(hours_of_day, False)
        total = sum(hours_of_day)
        return {
            "title": "When it's streamed",
            "caption": "How its streaming spreads over the hours of the day, UTC, in the last 4 weeks. Busiest"
                f" {_clock(busiest)}–{_clock(busiest + HOURS_WINDOW)}, quietest"
                f" {_clock(quietest)}–{_clock(quietest + HOURS_WINDOW)}.",
            "summary": f"Its streaming by hour of the day, UTC: busiest {_clock(busiest)} to"
                f" {_clock(busiest + HOURS_WINDOW)}, quietest {_clock(quietest)} to {_clock(quietest + HOURS_WINDOW)}",
            "bars": [
                {
                    "label": f"{_clock(hour)}–{_clock(hour + 1)} UTC",
                    "share": hours / total,
                    "value": f"{_percent(hours / total)} of its streaming",
                }
                for hour, hours in enumerate(hours_of_day)
            ],
            "axis": ["00:00", "06:00", "12:00", "18:00", "24:00 UTC"],
        }

    def _weeks(self) -> dict | None:
        weeks = self.numbers.get("weeks")
        if not weeks:
            return None
        top = max(weeks) or 1
        return {
            "title": "Streamers each week",
            "caption": "Different streamers who played it in each of the last 4 weeks, the newest first.",
            "bars": [
                {"label": label, "share": count / top, "value": f"{count:,}"}
                for label, count in zip(WEEK_LABELS, weeks)
            ],
        }

    def _also_played(self) -> dict | None:
        games = self.numbers.get("also_played")
        if not games:
            return None
        return {
            "title": "Streamers who played it also played",
            "caption": "Games its streamers played far more often than streamers in general did. Each links to its"
                " own page.",
            "games": [
                {
                    "name": game["name"],
                    "href": f"/game/{game['slug']}",
                    "detail": f"{game['streamers']:,} streamers, {round(game['lift'])}× as often" if index == 0
                        else f"{game['streamers']:,}, {round(game['lift'])}×",
                }
                for index, game in enumerate(games)
            ],
        }

    def _cta(self, streamers: int) -> dict:
        languages = self.numbers.get("languages") or {}
        return {
            "title": f"The {streamers:,} streamers who played it",
            "text": "Each one's viewers, streams and streaming days, ready to save as a list or export. Free, with your"
                " Twitch account.",
            "login_text": "Log in with Twitch to see them",
            "login_href": "/login?" + urlencode({"next": f"/game/{self.page.slug}"}),
            "search_text": "Open them in the search, one language at a time, with the other filters off:",
            "search_links": [
                {
                    "label": LANGUAGE_NAMES[code],
                    "streamers": f"{one['streamers']:,}",
                    # Every other filter off: any size, any average, from 1 stream and any hours.
                    "href": "/streamers?" + urlencode({
                        "game": self.game.host_game_id, "lang": code, "peak": "any", "streamsmin": 1, "hoursmin": "any",
                    }),
                }
                for code, one in sorted(languages.items(), key=lambda item: (-item[1]["streamers"], item[0]))
                if one["streamers"]
            ],
        }

    def _notes(self) -> dict:
        return {
            "title": "How these numbers are counted",
            "items": [
                f"Streams in the {len(PAGE_LANGUAGES)} broadcast languages the site covers count:"
                    f" {names_of(PAGE_LANGUAGES)}. A stream that played several games counts for each of them.",
                "Hours of play split each stream's length evenly between the categories it played, so a stream of"
                    " two games gives each half its time. When it's streamed counts each hour of the clock, UTC, in"
                    " which a stream was seen on the game.",
                "A streamer's size is their highest viewer count in the last 4 weeks. Indie games are those IGDB lists"
                    " in its Indie genre.",
                f"The games also played are those at least {ALSO_PLAYED_MIN_SHARED} of its streamers played, at least"
                    f" {ALSO_PLAYED_MIN_LIFT} times as often as streamers in general did.",
                "The numbers are rebuilt every 6 hours.",
            ],
        }


# The month by month history's tables: each column's name, and whether it holds numbers.
HISTORY_COLUMNS = (
    ("Month", False), ("Streamers", True), ("Streams", True), ("Hours played", True), ("Hours watched", True),
    ("Average viewers", True), ("Main languages", False),
)
LANGUAGE_COLUMNS = (
    ("Month", False), ("Streamers", True), ("Streams", True), ("Share of its streams", True), ("Hours played", True),
    ("Hours watched", True), ("Average viewers", True),
)


def _month_name(month) -> str:
    """A month as sentences write it: "October 2026"."""
    return f"{month:%B %Y}"


def _month_label(month) -> str:
    """A month as tables and bars write it: "Oct 2026"."""
    return f"{month:%b %Y}"


def _about_watched(hours: int) -> str:
    """Hours watched as the text rounds them: 10,649,191 to 10.6 million; fewer, as _about_hours does."""
    return f"{hours / 1_000_000:.1f} million" if hours >= 1_000_000 else _about_hours(hours)


def _columns(columns) -> list[dict]:
    return [{"label": label, "numeric": numeric} for label, numeric in columns]


class _Month:
    """A game's numbers in one month, in all the page languages or in one: zeros where it had none."""

    def __init__(self, row: GameMonthStats | None):
        self.streamers = row.streamers if row else 0
        self.streams = row.streams if row else 0
        self.hours = round(row.seconds / 3600) if row else 0
        self.watched = round(row.viewer_seconds / 3600) if row else 0
        self.viewers = round(row.viewer_seconds / row.snapshot_seconds) if row and row.snapshot_seconds else 0

    @property
    def detailed(self) -> bool:
        return self.streamers >= DETAIL_MIN_STREAMERS


class GameHistoryContent:
    """A game page's month by month section, from its GameMonthStats rows: every month counted
    from the archive files, from the first one it was streamed in, newest first. One table adds
    up the page languages; under it, one for each language that DETAIL_MIN_STREAMERS streamers
    played it in, in some month. The text says what stands out, each sentence only where the
    game's own numbers show it.

    A month below DETAIL_MIN_STREAMERS streamers, in all or in a language, shows its totals only,
    as the rest of the page does.
    """

    def __init__(self, game, name: str):
        self.game = game
        self.name = name
        self.rows = {(row.month, row.language): row for row in GameMonthStats.objects.filter(game=game)}
        counted = ArchivedMonth.objects.filter(stats_computed_at__isnull=False).order_by("month").values_list("month", flat=True)
        first = next((month for month in counted if (month, ALL_LANGUAGES) in self.rows), None)
        # Oldest first; the page shows them newest first.
        self.months = [month for month in counted if first is not None and month >= first]

    def _numbers(self, month, language=ALL_LANGUAGES) -> _Month:
        return _Month(self.rows.get((month, language)))

    def payload(self) -> dict | None:
        if not self.months:
            return None
        newest_first = list(reversed(self.months))
        top = max(self._numbers(month).streamers for month in self.months) or 1
        data_start = min((COLLECTED_SINCE[code] for code in PAGE_LANGUAGES if code in COLLECTED_SINCE), default=None)
        tables, others = self._language_tables()
        return {
            "title": f"{self.name} Twitch stats, month by month",
            "caption": f"Each month that is over, since {_month_name(self.months[0])}, in the languages the pages"
                " cover. The last 4 weeks are in the sections above.",
            "text": " ".join(self._sentences()),
            "bars": {
                "title": "Streamers each month",
                "caption": "Different streamers who played it in each month, the newest first.",
                "bars": [
                    {"label": _month_label(month), "share": self._numbers(month).streamers / top,
                     "value": f"{self._numbers(month).streamers:,}"}
                    for month in newest_first
                ],
            },
            "table": {
                "columns": _columns(HISTORY_COLUMNS),
                "rows": [{"month": self._label(month, data_start), "cells": self._main_cells(month)} for month in newest_first],
            },
            "by_language": {
                "title": "By language",
                "caption": f"A table for each language that {DETAIL_MIN_STREAMERS} or more streamers played it in, in"
                    " some month, the most played first.",
                "tables": tables,
                "others": others,
            } if tables or others else None,
            "hidden": HIDDEN,
            "hidden_hint": HIDDEN_HINT,
            "notes": self._notes(),
        }

    @staticmethod
    def _label(month, start) -> str:
        """A month's label; in the month counting began, after its 1st, the days counted, as in
        "16–31 Aug 2026"."""
        if start and (start.year, start.month) == (month.year, month.month) and start.day > 1:
            return f"{start.day}–{monthrange(month.year, month.month)[1]} {_month_label(month)}"
        return _month_label(month)

    def _came_out(self, month) -> bool:
        release = self.game.release_date
        return bool(release) and (release.year, release.month) == (month.year, month.month)

    @staticmethod
    def _detail_cells(one: _Month) -> list[str]:
        """Hours watched and average viewers; 0 when nobody streamed it, hidden for 1 to 4 streamers."""
        if not one.streamers:
            return ["0", "0"]
        if not one.detailed:
            return [HIDDEN, HIDDEN]
        return [f"{one.watched:,}", f"{one.viewers:,}"]

    def _main_cells(self, month) -> list[str]:
        one = self._numbers(month)
        if not one.streamers:
            languages = "None"
        elif not one.detailed:
            languages = HIDDEN
        else:
            ranked = sorted(
                ((self._numbers(month, code).streams, code) for code in PAGE_LANGUAGES),
                key=lambda item: (-item[0], PAGE_LANGUAGES.index(item[1])),
            )
            languages = " · ".join(
                f"{LANGUAGE_NAMES[code]} {_percent(streams / one.streams)}" for streams, code in ranked[:2] if streams
            )
        return [f"{one.streamers:,}", f"{one.streams:,}", f"{one.hours:,}", *self._detail_cells(one), languages]

    # The tables by language.

    def _language_tables(self) -> tuple[list[dict], str | None]:
        totals = {code: sum(self._numbers(month, code).streamers for month in self.months) for code in PAGE_LANGUAGES}
        played = [code for code in PAGE_LANGUAGES if totals[code]]
        shown = sorted(
            (code for code in played if max(self._numbers(month, code).streamers for month in self.months) >= DETAIL_MIN_STREAMERS),
            key=lambda code: (-totals[code], PAGE_LANGUAGES.index(code)),
        )
        others = [LANGUAGE_NAMES[code] for code in played if code not in shown]
        return (
            [self._language_table(code) for code in shown],
            f"Also streamed in {_names(others)}, by fewer than {DETAIL_MIN_STREAMERS} streamers in every month." if others else None,
        )

    def _language_months(self, code) -> list:
        """The game's months from the one counting began in for the language."""
        start = COLLECTED_SINCE.get(code)
        return [month for month in self.months if start is None or (month.year, month.month) >= (start.year, start.month)]

    def _language_table(self, code) -> dict:
        start = COLLECTED_SINCE.get(code)
        months = self._language_months(code)
        return {
            "heading": f"{self.name} on Twitch in {LANGUAGE_NAMES[code]}",
            "text": self._language_sentences(code, months, start),
            "table": {
                "columns": _columns(LANGUAGE_COLUMNS),
                "rows": [
                    {"month": self._label(month, start), "cells": self._language_cells(month, code)}
                    for month in reversed(months)
                ],
            },
        }

    def _share(self, month, code) -> str:
        """The language's share of the game's streams that month."""
        every = self._numbers(month).streams
        return _percent(self._numbers(month, code).streams / every) if every else "0%"

    def _language_cells(self, month, code) -> list[str]:
        one = self._numbers(month, code)
        return [f"{one.streamers:,}", f"{one.streams:,}", self._share(month, code), f"{one.hours:,}", *self._detail_cells(one)]

    def _language_sentences(self, code, months, start) -> str:
        language = LANGUAGE_NAMES[code]
        numbers = {month: self._numbers(month, code) for month in months}
        peak = max(months, key=lambda month: (numbers[month].streamers, -month.toordinal()))
        latest = months[-1]
        sentences = []
        if start and (start.year, start.month) > (self.months[0].year, self.months[0].month):
            sentences.append(f"Counted from {day_month_year(start)}.")
        sentences.append(
            f"Its busiest month in {language} was {_month_name(peak)}"
            f"{', the month it came out' if self._came_out(peak) else ''},"
            f" with {_plural(numbers[peak].streamers, 'streamer', 'streamers')}."
        )
        if latest != peak:
            one = numbers[latest]
            if one.streamers:
                sentences.append(
                    f"In {_month_name(latest)}: {_plural(one.streamers, 'streamer', 'streamers')},"
                    f" {self._share(latest, code)} of its streams"
                    + (f", averaging {one.viewers:,} viewers." if one.detailed else ".")
                )
            else:
                last = max(month for month in months if numbers[month].streamers)
                sentences.append(f"Nobody streamed it in {language} after {_month_name(last)}.")
        return " ".join(sentences)

    # The text about all the page languages.

    def _sentences(self) -> list[str]:
        numbers = {month: self._numbers(month) for month in self.months}
        peak = max(self.months, key=lambda month: (numbers[month].streamers, -month.toordinal()))
        top = numbers[peak]
        watched = f", and viewers watched about {_about_watched(top.watched)} hours." if top.detailed and top.watched else "."
        if len(self.months) == 1:
            return [f"In {_month_name(peak)}, {_plural(top.streamers, 'streamer', 'streamers')} played it" + watched]

        index = self.months.index(peak)
        came_out = self._came_out(peak)
        before = numbers[self.months[index - 1]] if index else None
        busiest = (
            f"Its busiest month was {_month_name(peak)}{', the month it came out' if came_out else ''}:"
            f" {_plural(top.streamers, 'streamer', 'streamers')} played it"
        )
        if before and not came_out and before.streamers and top.streamers >= JUMP_RATIO * before.streamers:
            busiest += f", up from {before.streamers:,} in {_month_name(self.months[index - 1])}"
        sentences = [busiest + watched]

        steady = self._steady_sentence(numbers)
        if steady:
            sentences.append(steady)
        else:
            if came_out and index:
                earlier = [numbers[month].streamers for month in self.months[:index]]
                low, high = min(earlier), max(earlier)
                sentences.append(
                    f"Before then, {low:,} streamers a month played it." if low == high
                    else f"Before then, {low:,} to {high:,} streamers a month played it."
                )
            sentences.extend(filter(None, [self._after_peak_sentence(numbers, index), self._jump_sentence(numbers, index)]))
        sentences.extend(filter(None, [self._lead_sentence(numbers), self._viewers_sentence()]))
        return sentences

    def _steady_sentence(self, numbers) -> str | None:
        counts = [numbers[month].streamers for month in self.months]
        if len(counts) < STEADY_MIN_MONTHS or min(counts) < STEADY_MIN_STREAMERS or max(counts) > STEADY_RATIO * min(counts):
            return None
        return f"Between {min(counts):,} and {max(counts):,} streamers played it every month."

    def _after_peak_sentence(self, numbers, index) -> str | None:
        later = [numbers[month].streamers for month in self.months[index + 1:]]
        if not later:
            return None
        if max(later) < DETAIL_MIN_STREAMERS:
            return "Nobody streamed it in the months after." if not max(later) else (
                f"In the months after, at most {_plural(max(later), 'streamer', 'streamers')} a month played it."
            )
        latest, peak = self.months[-1], self.months[index]
        return (
            f"In {_month_name(latest)}, {_plural(numbers[latest].streamers, 'streamer', 'streamers')} played it,"
            f" {_percent(numbers[latest].streamers / numbers[peak].streamers)} as many as in {_month_name(peak)}."
        )

    def _jump_sentence(self, numbers, index) -> str | None:
        """The latest month after the busiest one whose streamers more than doubled."""
        for position in range(len(self.months) - 1, index + 1, -1):
            month, previous = self.months[position], self.months[position - 1]
            now, before = numbers[month].streamers, numbers[previous].streamers
            if before and now >= JUMP_MIN_STREAMERS and now >= JUMP_RATIO * before:
                return f"In {_month_name(month)}, its streamers more than doubled, from {before:,} to {now:,}."
        return None

    def _lead_sentence(self, numbers) -> str | None:
        """Since when a language other than its usual one has had most of its streams."""
        latest = self.months[-1]
        if not numbers[latest].detailed:
            return None

        def leader(month):
            streams, place, code = max((self._numbers(month, code).streams, -PAGE_LANGUAGES.index(code), code) for code in PAGE_LANGUAGES)
            return code if streams else None

        totals = {code: sum(self._numbers(month, code).streams for month in self.months) for code in PAGE_LANGUAGES}
        usual = max(PAGE_LANGUAGES, key=lambda code: (totals[code], -PAGE_LANGUAGES.index(code)))
        now = leader(latest)
        if now is None or now == usual:
            return None
        start = latest
        for month in reversed(self.months[:-1]):
            if not numbers[month].detailed or leader(month) != now:
                break
            start = month
        new, old = LANGUAGE_NAMES[now], LANGUAGE_NAMES[usual]
        if start == latest:
            return f"In {_month_name(latest)}, more of its streams were in {new} than in {old}."
        return f"Since {_month_name(start)}, more of its streams have been in {new} than in {old}."

    def _viewers_sentence(self) -> str | None:
        """A language whose streams drew far more viewers than those of the language most of its
        streamers streamed it in, in the latest month with DETAIL_MIN_STREAMERS."""
        latest = next((month for month in reversed(self.months) if self._numbers(month).detailed), None)
        if latest is None:
            return None
        shown = [(code, self._numbers(latest, code)) for code in PAGE_LANGUAGES]
        shown = [(code, one) for code, one in shown if one.detailed and one.viewers]
        if len(shown) < 2:
            return None
        main_code, main = max(shown, key=lambda item: (item[1].streamers, -PAGE_LANGUAGES.index(item[0])))
        code, best = max(shown, key=lambda item: (item[1].viewers, -PAGE_LANGUAGES.index(item[0])))
        if code == main_code or best.viewers < VIEWERS_RATIO * main.viewers:
            return None
        return (
            f"In {_month_name(latest)}, its {LANGUAGE_NAMES[code]} streams averaged {best.viewers:,} viewers,"
            f" against {main.viewers:,} in {LANGUAGE_NAMES[main_code]}."
        )

    @staticmethod
    def _notes() -> list[str]:
        starts = {}
        for code in PAGE_LANGUAGES:
            starts.setdefault(COLLECTED_SINCE.get(code), []).append(LANGUAGE_NAMES[code])
        parts = [
            f"from {day_month_year(day)} in {_names(names)}"
            for day, names in sorted(starts.items(), key=lambda item: item[0] or date.min)
            if day is not None
        ]
        counted = parts[0] if len(parts) == 1 else "; ".join(parts[:-1]) + f"; and {parts[-1]}"
        return [
            f"Counted {counted}.",
            "Hours watched add up the time every viewer spent watching it. Average viewers is how many people"
                " watched one of its streams at once, on average.",
            f"0 means nobody streamed it that month, or nobody in that language. {HIDDEN} means 1 to"
                f" {DETAIL_MIN_STREAMERS - 1} streamers did, so only their totals are shown.",
        ]


def page_content(page: GamePage) -> dict:
    """The page the API serves for one GamePage row: a few indexed reads. Its past months come
    whatever the last 4 weeks hold, as each month has its own totals-only rule."""
    genres = sorted(page.game.genres.values_list("host_name", flat=True))
    content = GamePageContent(page, baselines(), genres).payload()
    content["history"] = GameHistoryContent(page.game, content["name"]).payload()
    return content
