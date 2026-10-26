from .base import BaseCachedPageBuilder
from .list_form import list_form_labels
from apps.userlists.views.list_entry import MAX_NOTE


class ListOfStreamersPageBuilder(BaseCachedPageBuilder):
    key = "list_of_streamers"
    log_label = "List of streamers page"

    def build_content(self) -> dict:
        return {
            "info": "{count} streamers · created {date}",
            "info_one": "1 streamer · created {date}",
            "saved_from": "Saved from",
            "list_actions": {
                "edit_btn": "Edit list",
                "delete_btn": "Delete list",
                "delete_confirm": "Delete this list and your notes on its streamers? This cannot be undone.",
                "delete_error": "Couldn't delete the list. Reload the page and try again.",
                "form": list_form_labels(
                    submit_btn="Save changes",
                    error="Couldn't save the changes. Reload the page and try again.",
                ),
            },
            "empty": "No streamers in this list yet. Add them from the search results or from"
                " a streamer's profile.",
            "empty_cta": "Search streamers",
            "view_profile": "View Profile",
            "remove_btn": "Remove from list",
            "remove_confirm": "Remove this streamer from the list? Your note on them goes too.",
            "remove_error": "Couldn't remove the streamer. Reload the page and try again.",
            "show_more": "Show More",
            "loading": "Loading...",
            "load_error": "Couldn't load more streamers. Reload the page and try again.",
            "no_stats": "No streams in this list's language in the last 4 weeks.",
            # A list made by hand shows each streamer in their main language, so
            # this one means no streams in any language.
            "no_stats_any": "No streams in the last 4 weeks.",
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
