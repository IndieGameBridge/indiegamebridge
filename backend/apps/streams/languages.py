"""The broadcast languages IndieGameBridge collects from Twitch, and the ones its pages
offer so far."""

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
# and chart. A language joins them once it has been collected long enough to show; till
# then its streams are collected and its stats built, but no page lists it. Portuguese,
# Japanese, Italian and Chinese are collected from 2026-11-02.
PAGE_LANGUAGES = ("en", "fr", "de", "es")
