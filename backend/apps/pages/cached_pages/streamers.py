from .base import BaseCachedPageBuilder
from .list_form import list_form_labels
from apps.streams.search import StreamerSearch


class StreamersPageBuilder(BaseCachedPageBuilder):
    key = "streamers"
    log_label = "Streamers page"

    def build_content(self) -> dict:
        filters_config, _ = StreamerSearch.get_filters_config()
        return {
            "title": "Search Streamers",
            "description": "Filter Twitch streamers by genre, language, and audience size.",
            "search_form": {
                "title": "Search Streamers",
                "aria_label": "Search streamers form",
                "filters": filters_config,
                "btn_text": "Apply Filters",
                "demo_title": "",
                "search_notes": [
                    "Results are based on each streamer's streams from the last 4 weeks.",
                    "Picking a second or third genre narrows the results: only streamers who"
                        " played all of the chosen genres in that window are shown.",
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
            "save_list": {
                "open_btn": "Save as list",
                "note": "Saves every streamer this search found, in the order shown. The list is"
                    " a snapshot and won't change when the search results do.",
                **list_form_labels(
                    submit_btn="Save list",
                    error="Couldn't save the list. Reload the page and try again.",
                ),
            },
        }
