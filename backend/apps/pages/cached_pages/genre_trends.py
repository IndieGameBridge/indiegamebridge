from .base import BaseCachedPageBuilder
from apps.streams.distribution import LANGUAGES
from apps.streams.models import GameGenre, GenreStats

# Human-readable labels for the languages the page breaks each genre down by. Keyed by
# the same ISO 639-1 codes as distribution.LANGUAGES; drives the chart legend.
LANGUAGE_LABELS = {"en": "English", "fr": "French", "de": "German", "es": "Spanish"}


class GenreTrendsPageBuilder(BaseCachedPageBuilder):
    """Public Genre Trends page: three per-genre diagrams over the last 4 weeks.

    Reads the precomputed GenreStats rows (built by rebuild_genre_stats) and shapes
    them into chart-ready payloads. Each genre's activity is broken down by broadcast
    language (English / French / German / Spanish) so a diagram shows one coloured bar per language
    instead of a single combined bar. Every defined genre is shown, including zero-value
    ones, so the page also tells the 'this genre was never popular' story. Each diagram
    is sorted high-to-low (by the genre's total across languages) so the most-streamed
    genres lead.
    """

    key = "genre_trends"
    log_label = "Genre Trends page"

    def build_content(self) -> dict:
        genre_names = list(
            GameGenre.objects.values_list("host_name", flat=True)
        )
        rows = list(
            GenreStats.objects
            .select_related("genre")
            .filter(language__in=LANGUAGES)
            .values_list(
                "genre__host_name",
                "language",
                "streams_count",
                "streamers_count",
                "total_duration_seconds",
            )
        )
        languages = [{"code": code, "label": LANGUAGE_LABELS[code]} for code in LANGUAGES]

        return {
            "title": "Genre Trends",
            "description": "How Twitch game genres compare by real streaming activity over the last 4 weeks.",
            # SEO <title> / meta description, kept separate from the visible
            # header above (which doubles as the page's h1/intro).
            "seo_title": "Twitch Game Genre Trends & Streaming Stats | IndieGameBridge",
            "seo_description": "Compare Twitch game genres by real streaming activity - streams, streamers, and "
                "hours per genre over the last 4 weeks, by language (English, French, German, Spanish).",
            "intro": "Wondering which game genres are most popular on Twitch right now? The charts below rank every"
                " genre we track by real streaming activity over the last 4 weeks - not just viewer counts, but how many"
                " streams happened, how many distinct streamers took part, and how many hours they broadcast. Each genre"
                " is broken down by broadcast language - English, French, German and Spanish - so you can see where its audience"
                " actually is. For indie game developers, that shows where an engaged streamer audience already exists for"
                " games like yours, and which genres are worth focusing your outreach on. The data is rebuilt daily from"
                " live Twitch streams.",
            "faq": {
                "title": "Frequently asked questions",
                "items": [
                    {
                        "question": "Which game genres are most streamed on Twitch?",
                        "answer": "The charts above rank genres by number of streams, distinct streamers, and hours"
                            " broadcast over the last 4 weeks. The leading genres shift over time, so the data is"
                            " recomputed daily from live Twitch streams rather than fixed all-time totals.",
                    },
                    {
                        "question": "How is genre streaming activity measured?",
                        "answer": "We poll live Twitch streams every 20 minutes via the official Helix API and record the"
                            " game, viewer count, and time of each snapshot. Each stream's time is split across the genres"
                            " it actually played, and non-game time such as Just Chatting is excluded.",
                    },
                    {
                        "question": "How often is the genre data updated?",
                        "answer": "Genre trends are recomputed daily and always cover a rolling 4-week window, so they"
                            " reflect current streaming activity rather than all-time totals.",
                    },
                    {
                        "question": "Which languages are included in the genre trends?",
                        "answer": "Each chart splits a genre's activity across the four broadcast languages we currently"
                            " track - English, French, German and Spanish. Streams in other languages aren't counted, so"
                            " the totals reflect those four audiences.",
                    },
                    {
                        "question": "How can indie developers use genre trends?",
                        "answer": "A genre with many active streamers and hours streamed is one where an engaged audience"
                            " already exists. Indie developers can use these trends to focus outreach on the genres - and"
                            " the streamers - that best match their game.",
                    },
                ],
            },
            "diagrams": [
                {
                    "title": "Streams per genre",
                    "description": "Number of streams in the last 4 weeks that played at least one game of"
                        " each genre, split by broadcast language. A stream spanning several genres counts toward each.",
                    "y_label": "Streams",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=2),
                },
                {
                    "title": "Streamers per genre",
                    "description": "Distinct streamers who broadcast at least one game of each genre in the"
                        " last 4 weeks, split by broadcast language.",
                    "y_label": "Streamers",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=3),
                },
                {
                    "title": "Hours streamed per genre",
                    "description": "Total hours broadcast per genre in the last 4 weeks, split by broadcast language."
                        " Each stream's time is split across the genres it actually played; non-game time"
                        " (e.g. Just Chatting) is excluded.",
                    "y_label": "Hours",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=4, to_hours=True),
                },
            ],
        }

    @staticmethod
    def _bars(genre_names, rows, value_index: int, to_hours: bool = False) -> list[dict]:
        # One bar per genre, each carrying a per-language value map. Seed every defined
        # genre with zeros for all languages so genres with no activity still render
        # (and every bar has the full language set the legend expects).
        by_genre = {name: {code: 0 for code in LANGUAGES} for name in genre_names}
        for row in rows:
            name, language = row[0], row[1]
            if name not in by_genre or language not in by_genre[name]:
                continue
            value = row[value_index]
            if to_hours:
                value = round(value / 3600)
            by_genre[name][language] = value

        bars = [{"x": name, "values": values} for name, values in by_genre.items()]
        bars.sort(key=lambda bar: sum(bar["values"].values()), reverse=True)
        return bars
