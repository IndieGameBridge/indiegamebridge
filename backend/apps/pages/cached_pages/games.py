from collections import defaultdict
from datetime import date, datetime, time, timezone as dt_timezone

from django.db import connection
from django.utils import timezone

from .base import BaseCachedPageBuilder
from .pagination import pagination_labels
from apps.streams.game_search import GameSearch
from apps.streams.languages import LANGUAGE_NAMES, PAGE_LANGUAGES, collected_since, day_month_year, names_of
from apps.streams.management.commands.rebuild_game_stats import WINDOW_HOURS
from apps.streams.models import GameStats

WINDOW_DAYS = WINDOW_HOURS // 24

# The games a language page's "What stands out" sentences look at: its most streamed ones.
# Only these, because a game few streamers play can look a thousand times more popular in
# one language than elsewhere when one channel streams it all day.
STANDOUT_TOP = 20
# A game stands out when its place in the other languages is at least this many times its
# place here, plus STANDOUT_PLACE_GAP: #7 against #126 does, #2 against #9 doesn't.
STANDOUT_PLACE_FACTOR = 3
STANDOUT_PLACE_GAP = 10
STANDOUT_GAMES = 3
# A language collected for fewer days than this has too few streams to compare yet.
STANDOUT_MIN_DAYS = 7

# Each page language's most streamed games over the 4 weeks, with their place there and in
# the other page languages put together. A game's total is the streams live on it in each
# hour, added up. About half a second on the local copy.
STANDOUTS_SQL = """
    WITH totals AS (
        SELECT game_id, language, (SELECT sum(value) FROM unnest(streams) AS value) AS total
        FROM streams_gamestats
        WHERE size_group = %(any_size)s AND language = ANY(%(languages)s)
    ),
    here AS (
        SELECT language, game_id, row_number() OVER (PARTITION BY language ORDER BY total DESC, game_id) AS place
        FROM totals
    ),
    elsewhere AS (
        SELECT page.language, totals.game_id, sum(totals.total) AS total
        FROM unnest(%(languages)s::text[]) AS page(language)
        JOIN totals ON totals.language <> page.language
        GROUP BY page.language, totals.game_id
    ),
    elsewhere_place AS (
        SELECT language, game_id, row_number() OVER (PARTITION BY language ORDER BY total DESC, game_id) AS place
        FROM elsewhere
    )
    SELECT here.language, game.host_name, here.place, elsewhere_place.place
    FROM here
    JOIN streams_game AS game ON game.id = here.game_id
    LEFT JOIN elsewhere_place ON elsewhere_place.language = here.language AND elsewhere_place.game_id = here.game_id
    WHERE here.place <= %(top)s
    ORDER BY here.language, here.place
"""


class GamesPageBuilder(BaseCachedPageBuilder):
    """Public Games pages: which games are streamed most now, and when, hour by hour.

    The overview, /games, adds the languages up; each language has a page of its own,
    /games/<slug>, with its own copy in `language_pages`, so each can be found by searches
    for that language. This payload is only the pages' text and form: the results come from
    GameSearch on each request.
    """

    key = "games"
    log_label = "Games page"

    def build_content(self) -> dict:
        today = timezone.now().date()
        top_games = self._top_games()
        all_names = names_of(PAGE_LANGUAGES)
        return {
            "title": "Most Streamed Games on Twitch",
            "description": "Which games are streamed most right now, and at which hours, in every language.",
            # SEO <title> / meta description, kept separate from the visible header above.
            "seo_title": "Most Streamed Twitch Games by Hour and Language | IndieGameBridge",
            "seo_description": "See which games Twitch streamers play most right now, hour by hour over the last"
                f" 4 weeks, in {len(PAGE_LANGUAGES)} broadcast languages and by streamer size.",
            "intro": "See which games are streamed most right now, and when. Open a game to see how many streams"
                " were live on it in each hour of the last 4 weeks, in each language. A game that is busy in one"
                " language can be nearly empty in another, and the quiet hours are when a stream of it meets the"
                " fewest competitors.",
            "note": None,
            "language_pages": [
                self._language_page(code, today, self._standouts(code, top_games.get(code, []), today))
                for code in PAGE_LANGUAGES
            ],
            # Under the list on every Games page; the questions on the overview only, since Google
            # wants one marked-up copy of them.
            "guide": {
                "title": "How to use the Games page",
                "steps": [
                    {
                        "title": "Pick a language.",
                        "text": "The links above the form switch between all languages added up and each language"
                            " on a page of its own.",
                    },
                    {
                        "title": "Narrow the list.",
                        "text": "Filter by streamer size (Max Viewers), by up to three genres, by release year, or by"
                            " words in the game's name.",
                    },
                    {
                        "title": "Read the number.",
                        "text": "Each game's row shows how many streams were live on it in the newest hour. The numbers"
                            " are rebuilt every 6 hours, so that hour can be up to about 7 hours ago.",
                    },
                    {
                        "title": "Open a game.",
                        "text": "Its chart shows how many streams were live on it in every hour of the last 4 weeks,"
                            " in UTC or in your own time, for all languages or one. Under the chart, a game with a page"
                            " of its own links to it: who streamed it, in which languages and sizes.",
                    },
                ],
            },
            "faq": {
                "title": "Questions about the Games page",
                "items": [
                    {
                        "question": "Which games are streamed most on Twitch right now?",
                        "answer": "The list on this page. The games with the most streams live in the newest hour come"
                            " first, and if two have the same number, the hour before decides. It counts streams in"
                            f" {len(PAGE_LANGUAGES)} broadcast languages: {all_names}.",
                    },
                    {
                        "question": "What does a game's chart show?",
                        "answer": "How many streams were live on the game in each hour of the last 4 weeks, the newest"
                            " hours on the left. You can read it in UTC or in your own time, and for all languages or"
                            " one.",
                    },
                    {
                        "question": "When do streams of a game meet the fewest competitors?",
                        "answer": "In the chart's quiet hours, when few streams are live on that game. Weigh them"
                            " against the hours your audience is awake.",
                    },
                    {
                        "question": "What does Max Viewers mean here?",
                        "answer": "A streamer's highest viewer count in the last 4 weeks. Picking a size counts only"
                            " the streams of streamers in that size group.",
                    },
                    {
                        "question": "Which streams count?",
                        "answer": f"Streams in the {len(PAGE_LANGUAGES)} broadcast languages, on any Twitch category"
                            " that IGDB lists as a game. Time in categories that aren't games, such as Just"
                            " Chatting, isn't counted.",
                    },
                    {
                        "question": "How fresh are the numbers?",
                        "answer": "We check live Twitch streams every 20 minutes, and the games' numbers are rebuilt"
                            " every 6 hours.",
                    },
                ],
            },
            "search_form": {
                "aria_label": "Search games",
                # The page's language is chosen by the links above the form.
                "filters": [one for one in GameSearch.get_filters_config() if one["name"] != "lang"],
                "btn_text": "Apply Filters",
                "search_notes": [
                    "Games with the most streams in the newest hour come first. If two games have the same number,"
                        " the hour before decides, and so on back through the 4 weeks.",
                    "Picking a second or third genre narrows the results: only games with all of the chosen"
                        " genres are shown.",
                    "Max Viewers is a streamer's highest viewer count in the last 4 weeks.",
                    "Game Name finds the games with every word you type in their name, in any order, so hollow knight"
                        " also finds Hollow Knight: Silksong. Each game found keeps its number in the list, so you see"
                        " where it stands.",
                ],
            },
            "labels": {
                "found_count": "Found {count} games",
                "found_count_one": "Found 1 game",
                "no_results": "No game streamed in the last 4 weeks matches these filters.",
                "no_data": "The game numbers are being built. Check back soon.",
                "game_column": "Game",
                # Under an open chart, for a game with a page of its own.
                "game_page": "Who streamed {game}: their languages, sizes and hours",
                # Over the rows' numbers: each game's streams in the newest hour.
                "streams_column": "Live streams",
                "pagination": pagination_labels(),
                "chart": {
                    "language": "Language",
                    "all_languages": "All",
                    "loading": "Loading the chart...",
                    "error": "Couldn't load the chart. Try again.",
                    "empty": "No streams for this game with these filters in the last 4 weeks.",
                    "caption": "Each point is one hour: how many streams were live on this game. The chart opens on"
                        " the newest hours, on the left. Scroll right for older ones, back 4 weeks.",
                    "caption_all": "Pick one language to see every hour's number, or move over the chart.",
                    "utc": "UTC",
                    "your_time": "You",
                    "your_time_long": "your time",
                },
            },
        }

    @staticmethod
    def _top_games() -> dict[str, list[tuple[str, int, int | None]]]:
        """Each page language's most streamed games: (name, place here, place in the other
        languages, or None where they don't stream it), best first."""
        with connection.cursor() as cursor:
            cursor.execute(STANDOUTS_SQL, {
                "any_size": GameStats.ANY_SIZE,
                "languages": list(PAGE_LANGUAGES),
                "top": STANDOUT_TOP,
            })
            rows = cursor.fetchall()
        by_language = defaultdict(list)
        for language, name, place, elsewhere in rows:
            if name:
                by_language[language].append((name, place, elsewhere))
        return by_language

    @staticmethod
    def _standouts(code: str, games: list[tuple[str, int, int | None]], today: date) -> dict | None:
        """The language's most streamed game, and those of its top games that rank far lower
        in the other languages. None while the language has too few days to compare."""
        since = collected_since(code, today, WINDOW_DAYS)
        if not games or (since is not None and (today - since).days < STANDOUT_MIN_DAYS):
            return None
        label = LANGUAGE_NAMES[code]

        top_name, _, top_elsewhere = games[0]
        if top_elsewhere == 1:
            where = ", as it was in the other languages"
        elif top_elsewhere is None:
            where = ", a game the other languages didn't stream"
        else:
            where = f", which is #{top_elsewhere} in the other languages"
        games_text = [f"Over the last 4 weeks, the most streamed game in {label} was {top_name}{where}."]

        far = [
            (name, place, elsewhere) for name, place, elsewhere in games[1:]
            if elsewhere is None or elsewhere >= STANDOUT_PLACE_FACTOR * place + STANDOUT_PLACE_GAP
        ]
        far.sort(key=lambda game: -(game[2] - game[1]) if game[2] is not None else float("-inf"))
        if far:
            clauses = []
            for name, place, elsewhere in far[:STANDOUT_GAMES]:
                here = f"#{place} in {label}" if not clauses else f"#{place}"
                there = f"#{elsewhere} elsewhere" if elsewhere is not None else "isn't streamed elsewhere"
                if clauses and elsewhere is not None:
                    there = f"#{elsewhere}"
                clauses.append(f"{name} is {here} and {there}")
            games_text.append(f"Some of the games streamed most in {label} rank far lower elsewhere: {'; '.join(clauses)}.")
        else:
            games_text.append(f"The other games streamed most in {label} rank about as high in the other languages.")
        # The games, then on their own what the places count, easier to read than one block.
        return {
            "title": f"What stands out in {label}",
            "paragraphs": [
                " ".join(games_text),
                "These places add up the streams live on each game in every hour of the last 4 weeks, so they can"
                " differ from the list below, which puts the newest hour first.",
            ],
        }

    @staticmethod
    def _language_page(code: str, today: date, standouts: dict | None) -> dict:
        label = LANGUAGE_NAMES[code]
        since = collected_since(code, today, WINDOW_DAYS)
        return {
            "code": code,
            # The page's URL: /games/japanese.
            "slug": label.lower(),
            "label": label,
            "title": f"Most Streamed Games on Twitch in {label}",
            "description": f"Which games {label}-language streamers play most right now, and at which hours.",
            "seo_title": f"Most Streamed Twitch Games in {label} by Hour | IndieGameBridge",
            "seo_description": f"See which games {label}-language Twitch streamers play most right now, hour by hour"
                " over the last 4 weeks, by streamer size.",
            "intro": f"See which games {label}-language streamers play most right now, and when. Open a game to see"
                " how many streams were live on it in each hour of the last 4 weeks. The quiet hours are when a"
                " stream of it meets the fewest competitors, and the other languages show whether a game is"
                f" popular elsewhere but not yet in {label}.",
            "note": (
                f"{label} streams have been collected since {day_month_year(since)}, so these charts start then."
            ) if since else None,
            # Where its line starts on a chart, as whole hours since the Unix epoch.
            "since_hour": int(datetime.combine(since, time.min, dt_timezone.utc).timestamp()) // 3600 if since else None,
            "standouts": standouts,
        }
