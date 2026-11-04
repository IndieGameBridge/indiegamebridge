from datetime import date, datetime, time, timezone as dt_timezone

from django.utils import timezone

from .base import BaseCachedPageBuilder
from apps.streams.game_search import GameSearch
from apps.streams.languages import LANGUAGE_NAMES, PAGE_LANGUAGES, collected_since, day_month_year
from apps.streams.management.commands.rebuild_game_stats import WINDOW_HOURS

WINDOW_DAYS = WINDOW_HOURS // 24


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
        return {
            "title": "Games",
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
            "language_pages": [self._language_page(code, today) for code in PAGE_LANGUAGES],
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
                ],
            },
            "labels": {
                "found_count": "Found {count} games",
                "found_count_one": "Found 1 game",
                "no_results": "No games match these filters.",
                "no_data": "The game numbers are being built. Check back soon.",
                "game_column": "Game",
                "hours_caption": "Streams live in each hour, UTC",
                "show_more": "Show More",
                "loading": "Loading...",
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
    def _language_page(code: str, today: date) -> dict:
        label = LANGUAGE_NAMES[code]
        since = collected_since(code, today, WINDOW_DAYS)
        return {
            "code": code,
            # The page's URL: /games/japanese.
            "slug": label.lower(),
            "label": label,
            "title": f"Games in {label}",
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
        }
