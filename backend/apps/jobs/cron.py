"""The scheduled jobs the admin's Job runs pages know: the management commands cron
runs, how often the crontab runs each, and what each one's runs count.
fetch_twitch_streams has records and pages of its own, FetchRun.

Keep `every` in step with the crontab: a job whose latest run is a quarter of its
interval late shows as overdue. Keep the counts in step with the commands' count()
calls: a count missing here is still recorded, but not drawn.
"""

from datetime import timedelta
from typing import NamedTuple


class Job(NamedTuple):
    name: str
    # How often the crontab runs it; None for a recorded job JOBS doesn't list.
    every: timedelta | None
    # (key, label) of each count its runs report, in the order the page shows them.
    counts: tuple = ()


JOBS = (
    Job("categorize_games", timedelta(hours=1), (
        ("games", "Categorized as games"),
        ("non_games", "Categorized as not games"),
        ("unknown", "Left new, unknown to Helix"),
    )),
    Job("approve_streams", timedelta(hours=1), (
        ("approved", "Streams approved"),
        ("deleted", "Streams deleted, no game played"),
    )),
    Job("enrich_igdb_games", timedelta(hours=1), (
        ("enriched", "Games enriched from IGDB"),
        ("not_found", "Games IGDB has no record of"),
        ("streams_updated", "Streams given new genres"),
    )),
    Job("rebuild_search_stats", timedelta(hours=6), (
        ("rows", "Search rows"),
        ("written", "Search rows new or changed"),
        ("deleted", "Search rows deleted, no stream left"),
    )),
    # Daily, before update_cached_pages rebuilds the Genre Trends page.
    Job("rebuild_genre_stats", timedelta(days=1), (
        ("rows", "Genre and language rows"),
    )),
    Job("update_cached_pages", timedelta(days=1), (
        ("pages", "Pages rebuilt"),
    )),
    Job("refresh_distribution", timedelta(days=1)),
    Job("delete_expired_personal_data", timedelta(days=1), (
        ("sign_ins", "Sign-in records deleted"),
        ("contact_messages", "Contact messages deleted"),
        ("exports", "Export records deleted"),
    )),
    Job("remove_opted_out_from_archive", timedelta(weeks=1), (
        ("months", "Files rewritten"),
        ("streams", "Streams removed"),
    )),
    # The first Tuesday of the month: 28 or 35 days after the one before.
    Job("archive_streams", timedelta(days=35), (
        ("months", "Months archived"),
        ("streams", "Streams archived"),
    )),
    # Wednesdays, several runs in a row until the month is out.
    Job("delete_archived_streams", timedelta(weeks=1), (
        ("streams", "Streams deleted"),
        ("months", "Months out of Postgres"),
    )),
)

JOBS_BY_NAME = {job.name: job for job in JOBS}


def every_text(every):
    """How often a job runs: "Every 20 min", "Hourly", "Daily", "Weekly", "Monthly"."""
    if every is None:
        return "No schedule"
    if every < timedelta(hours=1):
        return f"Every {round(every.total_seconds() / 60)} min"
    for interval, text in (
        (timedelta(hours=1), "Hourly"), (timedelta(days=1), "Daily"), (timedelta(weeks=1), "Weekly"),
    ):
        if every == interval:
            return text
    if every >= timedelta(days=28):
        return "Monthly"
    if every < timedelta(days=1):
        return f"Every {every.total_seconds() / 3600:g} h"
    return f"Every {every.days} days"
