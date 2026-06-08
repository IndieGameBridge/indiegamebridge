from .base import BaseCachedPageBuilder
from apps.streams.search import StreamerSearch


class StreamersPageBuilder(BaseCachedPageBuilder):
    key = "streamers"
    log_label = "Streamers page"

    def build_content(self) -> dict:
        filters_config, _ = StreamerSearch.get_filters_config()
        return {
            "title": "Search Streamers",
            "search_form": {
                "title": "Search Streamers",
                "aria_label": "Search streamers form",
                "filters": filters_config,
                "btn_text": "Apply Filters",
                "demo_title": "",
                "search_notes": [
                    "Results are based on each streamer's streams from the last 4 weeks."
                ],
                "demo_note": "",
                "cta_link_text": "",
            },
            "results_labels": {
                "found_count": "Found {count} streamers",
                "view_profile": "View Profile",
                "show_more": "Show More",
                "loading": "Loading...",
            },
        }
