from .base import BaseCachedPageBuilder
from apps.userlists.views.list_entry import MAX_NOTE


class ListOfStreamersPageBuilder(BaseCachedPageBuilder):
    key = "list_of_streamers"
    log_label = "List of streamers page"

    def build_content(self) -> dict:
        return {
            "info": "{count} streamers · saved {date}",
            "saved_from": "Saved from",
            "view_profile": "View Profile",
            "show_more": "Show More",
            "loading": "Loading...",
            "load_error": "Couldn't load more streamers. Reload the page and try again.",
            "no_stats": "No streams in this list's language in the last 4 weeks.",
            "removed": "Removed streamer",
            "removed_note": "This streamer opted out, so their details are gone. Your note stays.",
            "note_label": "Note",
            "add_note": "Add note",
            "edit_note": "Edit note",
            "note_placeholder": "Contact details, or what came of reaching out.",
            "save_note": "Save note",
            "saving": "Saving...",
            "cancel": "Cancel",
            "note_error": "Couldn't save the note. Copy your text, reload the page and try again.",
            # The endpoint's own limit, so the textarea stops overlong input as it
            # is typed rather than bouncing it back as a 400.
            "note_max_length": MAX_NOTE,
        }
