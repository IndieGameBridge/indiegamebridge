"""The per-game public pages, /game/<slug>: which games get one, their addresses, and what a
page says. rebuild_game_pages computes each page's numbers into its GamePage row every 6 hours;
page_content() turns a row into the page the API serves.

A page compares its game with a baseline: indie games for a game IGDB lists in the Indie genre,
every game for the rest.
"""

from urllib.parse import urlencode

from django.db.models import Count
from django.utils.text import slugify

from apps.streams.languages import LANGUAGE_NAMES, PAGE_LANGUAGES, day_month_year, names_of
from apps.streams.models import GamePage, JsonCache
from apps.streams.size_groups import PEAK_THRESHOLDS, SIZE_GROUPS

# A game gets a page the first time this many different streamers played it in 4 weeks.
PAGE_MIN_STREAMERS = 10
# From this many streamers in the 4 weeks, a page shows more than totals and asks search engines
# to index it. Below it, a public page could describe one or two people's habits, and it has too
# little to say to be worth finding.
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

WEEK_LABELS = ("4 weeks ago", "3 weeks ago", "2 weeks ago", "Last week")


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
            "indexable": self.details,
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
            return f"Nobody streamed {name} on Twitch in the last 4 weeks."
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
        oldest_first = list(reversed(weeks))
        top = max(oldest_first) or 1
        return {
            "title": "Streamers each week",
            "caption": "Different streamers who played it in each of the last 4 weeks.",
            "bars": [
                {"label": label, "share": count / top, "value": f"{count:,}"}
                for label, count in zip(WEEK_LABELS, oldest_first)
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


def page_content(page: GamePage) -> dict:
    """The page the API serves for one GamePage row: a few indexed reads."""
    genres = sorted(page.game.genres.values_list("host_name", flat=True))
    return GamePageContent(page, baselines(), genres).payload()
