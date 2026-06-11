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
