"""Text for the page picker under a long list: Previous, a dropdown of the pages, Next.

The streamer search, the Games pages and a list's page all show their rows a page
at a time with the same component, so its text is worded once here.
"""


def pagination_labels() -> dict:
    return {
        "aria_label": "Pages",
        "previous": "Previous",
        "next": "Next",
        "page": "Page",
        "of_pages": "of {pages}",
    }
