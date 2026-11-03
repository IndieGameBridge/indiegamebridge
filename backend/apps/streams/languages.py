"""The broadcast languages IndieGameBridge collects from Twitch, and the ones its pages
offer."""

from datetime import date

# Every language fetch_twitch_streams collects, by ISO 639-1 code - the code Twitch
# gives a stream's language, and Stream.language keeps - with its name, in the order
# the pages list them.
LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ja": "Japanese",
    "it": "Italian",
    "zh": "Chinese",
}

# The ones the pages offer: the search form, Genre Trends, and the home page's numbers
# and chart. A language added to LANGUAGE_NAMES stays out of here until it has been
# collected long enough to show; till then its streams are collected and its stats
# built, but no page lists it.
PAGE_LANGUAGES = ("en", "fr", "de", "es", "pt", "ja", "it", "zh")

# When collecting began, for the languages added after the first four. Until a
# language's 4-week window has filled, the pages showing it say so.
COLLECTED_SINCE = {
    "pt": date(2026, 11, 2),
    "ja": date(2026, 11, 2),
    "it": date(2026, 11, 2),
    "zh": date(2026, 11, 2),
}


def collected_since(code: str, today: date, window_days: int) -> date | None:
    """When collecting began for a language whose window of `window_days` hasn't
    filled yet by `today`; None once it has, and for the languages collected from the
    start."""
    since = COLLECTED_SINCE.get(code)
    return since if since is not None and (today - since).days < window_days else None


def day_month_year(day: date) -> str:
    """A date as pages write it: "2 November 2026"."""
    return f"{day.day} {day:%B %Y}"
