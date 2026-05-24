from .base import BaseCachedPageBuilder
from apps.streams.search import StreamerSearch


class StreamersPageBuilder(BaseCachedPageBuilder):
    key = "streamers"
    log_label = "Streamers page"

    def build_content(self) -> dict:
        filters_config, _ = StreamerSearch.get_filters_config()
        return {
            "title": "Search Streamers — IndieGameBridge",
            "search_form": {
                "title": "Search Streamers — IndieGameBridge",
                "aria_label": "Search streamers form",
                "filters": filters_config,
                "btn_text": "Apply Filters",
                "demo_title": "",
                "search_notes": [
                    "Times are in UTC. Days of week and the time window are both based on when each stream went offline. A UTC day can straddle two local days in non-UTC zones."
                ],
                "demo_note": "",
                "cta_link_text": "",
            },
            "search_results_title": "Search Results",
        }
