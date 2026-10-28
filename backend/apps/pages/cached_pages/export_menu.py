"""Text for the "Export" menu, which two pages show.

The search results put one beside the result count and a list's page puts one
with the list's own actions; both are the same component, so its text is
worded once here. The choices also tell it which formats to offer, in order.
"""


def export_menu_labels() -> dict:
    return {
        "open_btn": "Export",
        "choices": [
            {"file_format": "xlsx", "label": "Excel (.xlsx)"},
            {"file_format": "csv", "label": "CSV (.csv)"},
            {"file_format": "json", "label": "JSON (.json)"},
        ],
        "exporting": "Exporting...",
        "error": "Couldn't export the file. Try again.",
        "throttled": "That's the export limit for now. Try again in {minutes} min.",
    }
