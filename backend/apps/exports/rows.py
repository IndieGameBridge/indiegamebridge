"""The streamers an export writes: one dict per row, whatever the file format."""

from datetime import date, timedelta

from django.utils import timezone

from apps.streams.models import StreamerProfile
from apps.streams.search import MAX_RESULTS, StreamerSearch

TWITCH_CHANNEL_URL = "https://www.twitch.tv/{login}"

# Every export's columns in file order: the key a row holds, and its header.
# They stay put from one export to the next, so a fresh file lines up with an
# older copy someone has added their own columns to - the Twitch login first,
# as the column to match rows on. For the same reason, columns added later go
# at the very end, after a list's own.
_FIRST_COLUMNS = (
    ("twitch_login", "Twitch login"),
    ("display_name", "Display name"),
    ("twitch_url", "Twitch channel"),
    ("language", "Language"),
    ("max_viewers", "Max viewers"),
    ("avg_viewers", "Avg viewers"),
    ("hours_streamed", "Hours streamed"),
    ("streams", "Streams"),
    ("genres", "Genres"),
    ("twitch_user_id", "Twitch user ID"),
)

# The days of the last 28 a streamer started a stream on, the ones the results'
# strip fills: how many, and which.
DAY_COLUMNS = (
    ("days_streamed", "Days streamed (last 28)"),
    ("dates_streamed", "Dates streamed (UTC)"),
)

STREAMER_COLUMNS = (*_FIRST_COLUMNS, *DAY_COLUMNS)

# A list's entries add the owner's note and when each was added.
LIST_COLUMNS = (
    *_FIRST_COLUMNS,
    ("note", "Note"),
    ("added_at", "Added to list (UTC)"),
    *DAY_COLUMNS,
)


def search_rows(search: StreamerSearch) -> list[dict]:
    """Every streamer the search finds, in result order."""
    results = search.results(limit=MAX_RESULTS)
    twitch_user_ids = dict(
        StreamerProfile.objects.filter(id__in=[row["profile_id"] for row in results])
        .values_list("id", "host_user_id")
    )
    language = StreamerSearch.language_label(search.filters["lang"])
    return [
        _streamer_row(
            row["login"],
            row["display_name"],
            twitch_user_ids.get(row["profile_id"]),
            {**row, "language": language},
        )
        for row in results
    ]


def list_rows(list_of_streamers) -> list[dict]:
    """Every entry of the list in saved order, with the stats its page shows.

    As on the page (ListDetailView), each streamer is in the language of the
    search the list was saved from, or else in their main one. An entry whose
    streamer opted out keeps only the owner's note and date.
    """
    entries = list(list_of_streamers.entries.select_related("streamer_profile"))
    profile_ids = [entry.streamer_profile_id for entry in entries if entry.streamer_profile_id]
    language = None
    if list_of_streamers.search_filters:
        language = StreamerSearch(list_of_streamers.search_filters).filters["lang"]
    stats = StreamerSearch.stats_for_list(profile_ids, language)
    if language:
        # The file always names the language, where the page leaves the list's own unsaid.
        language_label = StreamerSearch.language_label(language)
        for one_stats in stats.values():
            one_stats.setdefault("language", language_label)

    rows = []
    for entry in entries:
        profile = entry.streamer_profile
        if profile is None:
            row = dict.fromkeys(key for key, _ in STREAMER_COLUMNS)
        else:
            row = _streamer_row(
                profile.host_login, profile.host_display_name, profile.host_user_id, stats.get(profile.id),
            )
        row["note"] = entry.description
        row["added_at"] = entry.added_at
        rows.append(row)
    return rows


def _streamer_row(login, display_name, twitch_user_id, stats) -> dict:
    """One streamer's columns; stats are None when there are no recent streams to count."""
    stats = stats or {}
    days_ago = stats.get("days_ago")
    return {
        "twitch_login": login,
        "display_name": display_name,
        "twitch_url": TWITCH_CHANNEL_URL.format(login=login),
        "language": stats.get("language"),
        "max_viewers": stats.get("peak_viewers"),
        "avg_viewers": stats.get("avg_viewers"),
        "hours_streamed": stats.get("hours_streamed"),
        "streams": stats.get("streams_count"),
        "genres": stats.get("genres"),
        # Text, as Twitch's API gives it: an id, not a number to add up.
        "twitch_user_id": None if twitch_user_id is None else str(twitch_user_id),
        "days_streamed": None if days_ago is None else len(days_ago),
        "dates_streamed": None if days_ago is None else _dates(days_ago),
    }


def _dates(days_ago: list[int]) -> list[date]:
    """The UTC dates of some days ago, oldest first: dates, so a file kept for a while
    still says when each stream was."""
    today = timezone.now().date()
    return sorted(today - timedelta(days=one_day) for one_day in days_ago)
