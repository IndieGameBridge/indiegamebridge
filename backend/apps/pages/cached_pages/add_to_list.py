"""Text for the "Add to list" menu, which two pages show.

The search results put one on every row and the streamer profile page puts one
in its header; both are the same component, so its text is worded once here.
"""


def add_to_list_labels() -> dict:
    return {
        "open_btn": "Add to list",
        "loading": "Loading your lists...",
        "load_error": "Couldn't load your lists. Close the menu and try again.",
        "no_lists": "You have no lists yet.",
        "no_lists_cta": "Start one on your dashboard",
        "in_list": "Added",
        "adding": "Adding...",
        "error": "Couldn't add the streamer. Close the menu and try again.",
    }
