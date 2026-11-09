"""Numbered pages for the API's long lists: search results, games, a list's streamers."""


def page_of(raw_page, total: int, page_size: int) -> tuple[int, int]:
    """The page asked for, kept within the pages there are, and how many there are.

    A page past the last one reads as the last one. An address can be left there
    by a list emptied from its end, or a search whose results shrank when they were
    rebuilt. Anything that isn't a number reads as the first page, and no rows at
    all still make one page, an empty one.
    """
    pages = max(1, -(-total // page_size))
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    return min(max(page, 1), pages), pages
