from .base import BaseCachedPageBuilder
from apps.streams.search import StreamerSearch
from apps.userlists.views.lists import MAX_DESCRIPTION, MAX_TITLE


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
                "title_label": "List title",
                "title_placeholder": "e.g. small shooter streamers",
                "description_label": "Note (optional)",
                "description_placeholder": "What is this list for?",
                "note": "Saves every streamer this search found, in the order shown. The list is"
                    " a snapshot and won't change when the search results do.",
                "submit_btn": "Save list",
                "saving": "Saving...",
                "cancel_btn": "Cancel",
                "error": "Couldn't save the list. Reload the page and try again.",
                # The endpoint's own limits, so the form stops overlong input as it
                # is typed rather than bouncing it back as a 400.
                "title_max_length": MAX_TITLE,
                "description_max_length": MAX_DESCRIPTION,
            },
        }
