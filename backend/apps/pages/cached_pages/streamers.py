from .add_to_list import add_to_list_labels
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
                "found_count_one": "Found 1 streamer",
                "view_profile": "View Profile",
                "show_more": "Show More",
                "loading": "Loading...",
            },
            "add_to_list": add_to_list_labels(),
            "save_list": {
                "open_btn": "Save to list",
                "new_list_btn": "Save as new list",
                "existing_list_btn": "Add to an existing list",
                "new_list": {
                    "note": "Saves every streamer this search found, in the order shown. The list"
                        " is a snapshot and won't change when the search results do.",
                    **list_form_labels(
                        submit_btn="Save list",
                        error="Couldn't save the list. Reload the page and try again.",
                    ),
                },
                "existing_list": {
                    "list_label": "List",
                    "list_placeholder": "Choose a list",
                    "note": "Adds every streamer this search found to the end of the list, in the"
                        " order shown. Streamers already in it are skipped.",
                    "submit_btn": "Add to list",
                    "saving": "Adding...",
                    "cancel_btn": "Cancel",
                    "loading": "Loading your lists...",
                    "load_error": "Couldn't load your lists. Reload the page and try again.",
                    "no_lists": "You have no lists yet. Save these results as a new list instead.",
                    "error": "Couldn't add the streamers. Reload the page and try again.",
                    "done": "“{title}”: {added} added.",
                    "done_skipped": "“{title}”: {added} added, {skipped} already in the list.",
                    "open_list": "Open list",
                    "close_btn": "Close",
                },
            },
        }
