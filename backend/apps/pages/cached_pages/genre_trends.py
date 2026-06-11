from .base import BaseCachedPageBuilder
from apps.streams.models import GenreStats


class GenreTrendsPageBuilder(BaseCachedPageBuilder):
    """Public Genre Trends page: three per-genre diagrams over the last 4 weeks.

    Reads the precomputed GenreStats rows (built by rebuild_genre_stats) and shapes
    them into chart-ready payloads. Every defined genre is shown, including zero-value
    ones, so the page also tells the 'this genre was never popular' story. Each diagram
    is sorted high-to-low so the most-streamed genres lead.
    """

    key = "genre_trends"
    log_label = "Genre Trends page"

    def build_content(self) -> dict:
        rows = list(
            GenreStats.objects
            .select_related("genre")
            .values_list(
                "genre__host_name",
                "streams_count",
                "streamers_count",
                "total_duration_seconds",
            )
        )

        return {
            "title": "Genre Trends",
            "description": "How Twitch game genres compare by real streaming activity over the last 4 weeks.",
            # SEO <title> / meta description, kept separate from the visible
            # header above (which doubles as the page's h1/intro).
            "seo_title": "Twitch Game Genre Trends & Streaming Stats | IndieGameBridge",
            "seo_description": "See how Twitch game genres compare by real streaming activity: number of "
                "streams, distinct streamers, and hours broadcast per genre over the last 4 weeks. Updated daily.",
            "intro": "Wondering which game genres are most popular on Twitch right now? The charts below rank every"
                " genre we track by real streaming activity over the last 4 weeks - not just viewer counts, but how many"
                " streams happened, how many distinct streamers took part, and how many hours they broadcast. For indie"
                " game developers, that shows where an engaged streamer audience already exists for games like yours,"
                " and which genres are worth focusing your outreach on. The data is rebuilt daily from live Twitch streams.",
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
                        " each genre. A stream spanning several genres counts toward each.",
                    "y_label": "Streams",
                    "bars": self._bars(rows, value_index=1),
                },
                {
                    "title": "Streamers per genre",
                    "description": "Distinct streamers who broadcast at least one game of each genre in the"
                        " last 4 weeks.",
                    "y_label": "Streamers",
                    "bars": self._bars(rows, value_index=2),
                },
                {
                    "title": "Hours streamed per genre",
                    "description": "Total hours broadcast per genre in the last 4 weeks. Each stream's time is"
                        " split across the genres it actually played; non-game time (e.g. Just Chatting) is excluded.",
                    "y_label": "Hours",
                    "bars": self._bars(rows, value_index=3, to_hours=True),
                },
            ],
        }

    @staticmethod
    def _bars(rows, value_index: int, to_hours: bool = False) -> list[dict]:
        bars = []
        for row in rows:
            value = row[value_index]
            if to_hours:
                value = round(value / 3600)
            bars.append({"x": row[0], "y": value})
        bars.sort(key=lambda bar: bar["y"], reverse=True)
        return bars
