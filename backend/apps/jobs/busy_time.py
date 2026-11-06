"""The admin's Job runs > Busy time page: which jobs ran in each minute of a three-hour
window, to find the free minutes for a deploy, a heavy task run by hand or a new cron job."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta, timezone as dt_timezone

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.fetch import graphs as fetch_page
from apps.fetch.models import FetchRun
from apps.jobs.graphs import FETCH, NEVER_FINISHED_AFTER, known_jobs
from apps.jobs.models import JobRun
from core.utils.admin_charts import (
    Cell,
    Figure,
    HoverSource,
    LegendItem,
    MinuteTimeline,
    Tile,
    count_text,
    counted_text,
    day_text,
    duration_text,
    moment_text,
)

# The window, in minutes. It goes back a window at a time, for up to a week: long enough
# to reach the jobs that run on one day of the week.
WINDOW_MINUTES = 180
OFFSET_STEP_HOURS = 3
MAX_OFFSET_HOURS = 7 * 24

# The table leaves out free stretches shorter than this: too short to plan around.
LISTED_STRETCH = 5

# A minute's tooltip row holds whether it's free, then each job's runs in it.
FREE = 0


@dataclass
class _Run:
    """A JobRun or a FetchRun as the page shows it: the minutes of the window it took,
    and the line its tooltip gets."""

    job: str
    first: int
    last: int
    text: str
    failed: bool
    url: str


def _minute(moment, start):
    """Which minute of the window a moment falls in, the first being 0."""
    return (moment - start) // timedelta(minutes=1)


def _run(job, run, start, now, never_finished_after, change_url):
    never_finished = run.finished_at is None and now - run.started_at >= never_finished_after
    failed = never_finished or run.status == JobRun.Status.FAILED
    if never_finished:
        # All that's known of it is when it started.
        until, text = run.started_at, "Never finished"
    elif run.finished_at is None:
        until, text = now, "Running"
    else:
        until = run.finished_at
        text = ("Failed after " if failed else "") + duration_text(run.duration_seconds)
    return _Run(
        job,
        max(_minute(run.started_at, start), 0),
        min(_minute(until, start), WINDOW_MINUTES - 1),
        text,
        failed,
        change_url.replace("/0/", f"/{run.pk}/"),
    )


def _overlapping(model, start, end, never_finished_after):
    """The runs that may touch the window: ended inside it or later, or with no end yet."""
    return model.objects.filter(
        Q(finished_at__gte=start) | Q(finished_at__isnull=True, started_at__gte=start - never_finished_after),
        started_at__lt=end,
    )


def _taken_minutes(start, end, now):
    """The window's minutes each job took, with the runs in them: {job: {minute: [runs]}}."""
    fetch_url = reverse("admin:fetch_fetchrun_change", args=[0])
    job_url = reverse("admin:jobs_jobrun_change", args=[0])
    fetch_runs = _overlapping(FetchRun, start, end, fetch_page.NEVER_FINISHED_AFTER).only(
        "started_at", "finished_at", "duration_seconds", "status",
    )
    job_runs = _overlapping(JobRun, start, end, NEVER_FINISHED_AFTER).defer("counts", "output")
    runs = [
        *(_run(FETCH, run, start, now, fetch_page.NEVER_FINISHED_AFTER, fetch_url) for run in fetch_runs),
        *(_run(run.job, run, start, now, NEVER_FINISHED_AFTER, job_url) for run in job_runs),
    ]
    taken = {}
    for run in runs:
        for minute in range(run.first, run.last + 1):
            taken.setdefault(run.job, {}).setdefault(minute, []).append(run)
    return taken


def _stretches(minutes, color):
    """Sorted minutes as [first, length, color], a new stretch at each gap or new color."""
    stretches = []
    for minute in minutes:
        if stretches and sum(stretches[-1][:2]) == minute and stretches[-1][2] == color(minute):
            stretches[-1][1] += 1
        else:
            stretches.append([minute, 1, color(minute)])
    return stretches


def _offsets(first_started, now):
    """The hours the window can go back: not to before the first run recorded, since an
    earlier window would look free."""
    recorded = (now - first_started) // timedelta(hours=1)
    furthest = min(MAX_OFFSET_HOURS, recorded - OFFSET_STEP_HOURS)
    return [0, *range(OFFSET_STEP_HOURS, furthest + 1, OFFSET_STEP_HOURS)]


def _chosen_offset(raw, offsets):
    try:
        offset = int(raw)
    except (TypeError, ValueError):
        return 0
    return offset if offset in offsets else 0


def _offset_text(hours):
    """0 -> "Latest", 6 -> "6 hours ago", 27 -> "1 day 3 hours ago"."""
    if not hours:
        return "Latest"
    days, hours = divmod(hours, 24)
    parts = ([counted_text(days, "day")] if days else []) + ([counted_text(hours, "hour")] if hours else [])
    return f"{' '.join(parts)} ago"


def _range_text(start, end):
    if start.date() == end.date():
        return f"{day_text(start)}, {start:%H:%M} to {end:%H:%M} UTC"
    return f"{day_text(start)}, {start:%H:%M} to {day_text(end)}, {end:%H:%M} UTC"


def busy_time(raw_offset, now=None):
    """The Busy time page's context: the window ending now, or raw_offset hours before."""
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    context = {
        "breadcrumb": "Busy time",
        "page_links": [{"label": "Graphs", "href": reverse("admin:jobs_jobrun_graphs")}],
    }
    first_started = JobRun.objects.order_by("started_at").values_list("started_at", flat=True).first()
    if first_started is None:
        return {**context, "empty_text": "No job runs are recorded yet."}

    offsets = _offsets(first_started, now)
    offset = _chosen_offset(raw_offset, offsets)
    # The minute under way is the last one shown.
    end = now.replace(second=0, microsecond=0) + timedelta(minutes=1) - timedelta(hours=offset)
    start = end - timedelta(minutes=WINDOW_MINUTES)

    taken = _taken_minutes(start, end, now)
    names = [name for name in (FETCH, *(job.name for job in known_jobs())) if name in taken]
    free = [minute for minute in range(WINDOW_MINUTES) if not any(minute in minutes for minutes in taken.values())]
    free_stretches = _stretches(free, lambda minute: "series-3")

    timeline = MinuteTimeline(start, WINDOW_MINUTES, f"Which jobs ran in each minute, {_range_text(start, end)}")
    timeline.add_row("Free", free_stretches)
    for name in names:
        minutes = taken[name]
        timeline.add_row(name, _stretches(sorted(minutes), lambda minute: (
            "critical" if any(run.failed for run in minutes[minute]) else "series-1"
        )))

    source = HoverSource("minutes")
    for minute in range(WINDOW_MINUTES):
        by_job = [taken[name].get(minute, []) for name in names]
        runs = [run for of_job in by_job for run in of_job]
        source.add(
            timeline.minute_x(minute),
            moment_text(start + timedelta(minutes=minute)),
            [None if runs else "Free", *(", ".join(run.text for run in of_job) or None for of_job in by_job)],
            max(runs, key=lambda run: run.last - run.first).url if runs else None,
        )
    timeline.hover_on(source, [
        {"field": FREE, "label": "", "color": None},
        *({"field": index, "label": name, "color": "series-1"} for index, name in enumerate(names, start=1)),
    ])

    def clock(minute):
        return f"{start + timedelta(minutes=minute):%H:%M}"

    failed = any(run.failed for minutes in taken.values() for runs in minutes.values() for run in runs)
    return {
        **context,
        "select": {
            "name": "offset",
            "label": "Time offset",
            "options": [
                {"value": hours, "label": _offset_text(hours), "selected": hours == offset} for hours in offsets
            ],
        },
        "range_text": _range_text(start, end),
        "tiles": _tiles(free, free_stretches, taken, clock),
        "figures": [Figure(
            key="busy-time",
            title="Busy time",
            subtitle="What ran in each minute, a row for each job, under a row of the minutes nothing ran. A run"
                " takes its whole minute, even if it lasted a second, and runs made by hand count. Only recorded"
                " runs show, so not Postgres's autovacuum or the server's backups.",
            plots=[timeline],
            legend=[LegendItem("Failed or never finished", "critical", "rect")] if failed else [],
            table_title=f"Free stretches of {LISTED_STRETCH} minutes or more",
            table_headers=[Cell("From", number=False), Cell("To", number=False), "Minutes"],
            table_rows=[
                [clock(first), Cell(clock(first + length), number=False), count_text(length)]
                for first, length, _ in free_stretches
                if length >= LISTED_STRETCH
            ],
        )],
        "hover_sources": [source],
    }


def _tiles(free, free_stretches, taken, clock):
    jobs_at = Counter(minute for minutes in taken.values() for minute in minutes)
    longest = max(free_stretches, key=lambda stretch: stretch[1], default=None)
    return [
        Tile("Free minutes", count_text(len(free)), f"of {WINDOW_MINUTES}"),
        Tile(
            "Longest free stretch",
            f"{longest[1]} min" if longest else "None",
            f"{clock(longest[0])} to {clock(sum(longest[:2]))} UTC" if longest else "",
        ),
        Tile("Minutes with 2+ jobs", count_text(sum(jobs >= 2 for jobs in jobs_at.values()))),
    ]
