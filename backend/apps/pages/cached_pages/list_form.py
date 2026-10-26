"""Text for the list title-and-note form, which three pages show.

Saving a search as a list, starting an empty list on the dashboard and editing a
list all use one form component, so its fields are worded once here. Each page
passes the text that differs: the submit button and the failure message.
"""

from apps.userlists.views.lists import MAX_DESCRIPTION, MAX_TITLE


def list_form_labels(*, submit_btn: str, error: str) -> dict:
    return {
        "title_label": "List title",
        "title_placeholder": "e.g. small shooter streamers",
        "description_label": "Note (optional)",
        "description_placeholder": "What is this list for?",
        "submit_btn": submit_btn,
        "saving": "Saving...",
        "cancel_btn": "Cancel",
        "error": error,
        # The endpoint's own limits, so the form stops overlong input as it is
        # typed rather than bouncing it back as a 400.
        "title_max_length": MAX_TITLE,
        "description_max_length": MAX_DESCRIPTION,
    }
