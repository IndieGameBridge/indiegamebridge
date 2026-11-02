"""The admin's Job runs > Graphs page: how the scheduled jobs' runs went. For all of
them, a table: each job's runs in the time range, the failed ones, the time they took,
and its latest run, late or not. For one job, graphs: how long its runs took, which of
them failed, and what they did, day by day."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone as dt_timezone
from statistics import median
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from apps.fetch import graphs as fetch_page
from apps.fetch.models import FetchRun
from apps.jobs.cron import JOBS, JOBS_BY_NAME, Job, every_text
from apps.jobs.models import JobRun
from core.utils.admin_charts import (
    COLUMN_DAY_WIDTH,
    Cell,
    Figure,
    HoverSource,
    LegendItem,
    Plot,
    Tile,
    TimeAxis,
    count_text,
    counted_text,
    day_text,
    duration_text,
    moment_text,
)

# A run still RUNNING this long after it started was killed rather than slow.
NEVER_FINISHED_AFTER = timedelta(hours=3)

# A job is late once its latest run started this many of its intervals ago.
LATE_AFTER = 1.25

# Lines break where runs are further apart than this many of the job's intervals.
GAP = 2.25

# A job run more often than daily gets a point for each run, this many pixels after the
# one before; one run less often, a column for each day.
RUN_WIDTH = 10

# The values of a run's tooltip row, in this order.
RUN_TIME, STATUS, ARGUMENTS = range(3)

# The values of a day's, in this order, then the day's total of each of the job's counts.
DAY_TIME, DAY_RUNS, DAY_FAILED, FIRST_COUNT = range(4)

FETCH = "fetch_twitch_streams"


def _ago_text(delta):
    minutes = round(delta.total_seconds() / 60)
    if minutes < 90:
        return f"{minutes:,} min ago"
    hours = round(minutes / 60)
    return f"{hours} h ago" if hours < 48 else f"{round(hours / 24)} days ago"


def _latest_note(run, now, never_finished_after):
    """How a job's latest run went: a JobRun's, or a FetchRun's."""
    if run.duration_seconds is not None:
        return f"{run.get_status_display()}, {duration_text(run.duration_seconds)}"
    return "Running now" if now - run.started_at < never_finished_after else "Never finished"


def _time_unit(longest):
    """Minutes for runs of two minutes and longer, seconds for shorter ones: the seconds
    in the unit, its ticks' text and its name."""
    if longest >= 120:
        return 60, lambda value: "0" if value == 0 else f"{value:g} min", "minutes"
    return 1, lambda value: "0" if value == 0 else f"{value:g}s", "seconds"


def _window(days, first_started, now):
    """The page's first and last days, the last `days` of them but none before the first
    run recorded, and that run's day."""
    today = now.astimezone(dt_timezone.utc).date()
    tracked_from = first_started.astimezone(dt_timezone.utc).date()
    return max(today - timedelta(days=days - 1), tracked_from), today, tracked_from


def _range_text(first_day, last_day, tracked_from, recorded):
    text = f"{day_text(first_day)} to {day_text(last_day)}, UTC"
    if first_day == tracked_from:
        text += f". {recorded} are recorded from {day_text(tracked_from)}."
    return text


def _jobs():
    """The jobs the page knows: cron.JOBS, then any other job with runs recorded."""
    recorded = set(JobRun.objects.order_by().values_list("job", flat=True).distinct())
    return [*JOBS, *(Job(name, None) for name in sorted(recorded - set(JOBS_BY_NAME)))]


def job_graphs(days, job="", now=None):
    """The Job runs > Graphs page's context, for the last `days` days: the table of all
    the jobs, or the graphs of `job`."""
    now = now or timezone.now()
    jobs = _jobs()
    chosen = next((one for one in jobs if one.name == job), None)
    context = {
        "select": {
            "name": "job",
            "label": "Job",
            "options": [{"value": "", "label": "All jobs", "selected": chosen is None}] + [
                {"value": one.name, "label": one.name, "selected": one == chosen} for one in jobs
            ],
        },
    }
    context.update(_job_context(chosen, days, now) if chosen else _all_jobs_context(jobs, days, now))
    return context


@dataclass
class _Track:
    """A job's runs as the table of all the jobs sums them up: JobRuns, or FetchRuns."""

    name: str
    every: timedelta | None
    runs: list  # the time range's, oldest first
    latest: object  # the latest run of all, or None
    never_finished_after: timedelta
    graphs_url: str
    failed_url: str
    change_url: str  # a run's admin page, with 0 for its id

    def never_finished(self, run, now):
        return run.duration_seconds is None and now - run.started_at >= self.never_finished_after

    def late(self, now, recorded_since):
        """Whether the job's latest run, or the first it should have had, is overdue."""
        if self.every is None:
            return False
        since = self.latest.started_at if self.latest else recorded_since
        return now - since > self.every * LATE_AFTER


def _all_jobs_context(jobs, days, now):
    first_started = JobRun.objects.order_by("started_at").values_list("started_at", flat=True).first()
    if first_started is None:
        return {"empty_text": "No job runs are recorded yet."}
    first_day, today, tracked_from = _window(days, first_started, now)
    start = datetime.combine(first_day, time(), tzinfo=dt_timezone.utc)

    in_window = {}
    for run in JobRun.objects.filter(started_at__gte=start).defer("counts", "output").order_by("started_at"):
        in_window.setdefault(run.job, []).append(run)
    latest = {run.job: run for run in JobRun.objects.defer("counts", "output").order_by("job", "-started_at").distinct("job")}
    fetch_fields = ("started_at", "duration_seconds", "status")
    changelist_url = reverse("admin:jobs_jobrun_changelist")
    tracks = [_Track(
        name=FETCH,
        every=fetch_page.RUN_INTERVAL,
        runs=list(FetchRun.objects.filter(started_at__gte=start).only(*fetch_fields).order_by("started_at")),
        latest=FetchRun.objects.only(*fetch_fields).order_by("-started_at").first(),
        never_finished_after=fetch_page.NEVER_FINISHED_AFTER,
        graphs_url=f"{reverse('admin:fetch_fetchrun_graphs')}?days={days}",
        failed_url=f"{reverse('admin:fetch_fetchrun_changelist')}?status__exact={FetchRun.Status.FAILED}",
        change_url=reverse("admin:fetch_fetchrun_change", args=[0]),
    )] + [_Track(
        name=job.name,
        every=job.every,
        runs=in_window.get(job.name, []),
        latest=latest.get(job.name),
        never_finished_after=NEVER_FINISHED_AFTER,
        graphs_url="?" + urlencode({"job": job.name, "days": days}),
        failed_url=f"{changelist_url}?" + urlencode({"job": job.name, "status__exact": JobRun.Status.FAILED}),
        change_url=reverse("admin:jobs_jobrun_change", args=[0]),
    ) for job in jobs]

    rows, total_runs, failed, never_finished, ran, late = [], 0, 0, 0, 0, []
    for track in tracks:
        # One still running is left out until it ends, or is known never to.
        shown = [run for run in track.runs if run.duration_seconds is not None or track.never_finished(run, now)]
        durations = [run.duration_seconds for run in shown if run.duration_seconds is not None]
        failed_now = sum(run.status == JobRun.Status.FAILED or track.never_finished(run, now) for run in shown)
        total_runs += len(shown)
        failed += failed_now
        never_finished += sum(track.never_finished(run, now) for run in shown)
        ran += bool(shown)
        is_late = track.late(now, first_started)
        if is_late:
            late.append(track.name)

        if track.latest is None:
            latest_cells = [
                Cell("None yet, overdue" if is_late else "None yet", marker="warning" if is_late else "", number=False),
                Cell("-", number=False),
            ]
        else:
            latest_failed = track.latest.status == JobRun.Status.FAILED or track.never_finished(track.latest, now)
            latest_cells = [
                Cell(
                    _ago_text(now - track.latest.started_at) + (", overdue" if is_late else ""),
                    track.change_url.replace("/0/", f"/{track.latest.pk}/"),
                    "warning" if is_late else "",
                    number=False,
                ),
                Cell(
                    _latest_note(track.latest, now, track.never_finished_after),
                    marker="critical" if latest_failed else "",
                    number=False,
                ),
            ]
        rows.append([
            Cell(track.name, track.graphs_url, number=False),
            Cell(every_text(track.every), number=False),
            count_text(len(shown)),
            Cell(count_text(failed_now), track.failed_url if failed_now else "", "critical" if failed_now else ""),
            duration_text(median(durations)) if durations else "-",
            duration_text(max(durations)) if durations else "-",
            *latest_cells,
        ])

    return {
        "range_text": _range_text(first_day, today, tracked_from, "Job runs"),
        "tiles": [
            Tile("Runs", count_text(total_runs), f"{ran:,} of {len(tracks):,} jobs ran"),
            Tile(
                "Failed", count_text(failed), f"{never_finished:,} never finished" if never_finished else "",
                "", "critical" if failed else "",
            ),
            Tile(
                "Overdue jobs", count_text(len(late)), ", ".join(late) if len(late) <= 2 else "",
                "", "warning" if late else "",
            ),
        ],
        "figures": [Figure(
            key="jobs",
            title="Jobs",
            subtitle="Each job's runs in the time range, the failed ones and the time they took, then its latest"
                " run, whenever that was. A job is overdue once its latest run is a quarter of its interval"
                " late. Pick a job above for its graphs; fetch_twitch_streams has a page of its own.",
            plots=[],
            table_headers=[
                "Job", Cell("Runs every", number=False), "Runs", "Failed", "Median time", "Longest",
                Cell("Latest run", number=False), Cell("How it went", number=False),
            ],
            table_rows=rows,
        )],
        "hover_sources": [],
    }


@dataclass
class _Run:
    """One of a job's runs as its graphs show it."""

    run: JobRun
    x: float
    never_finished: bool

    @property
    def finished(self):
        return self.run.duration_seconds is not None

    @property
    def duration(self):
        return self.run.duration_seconds

    @property
    def failed(self):
        return self.never_finished or self.run.status == JobRun.Status.FAILED

    def count(self, key):
        return self.run.counts.get(key, 0)

    def status_text(self):
        if self.never_finished:
            return "Never finished: the run is still marked running"
        if self.failed:
            return "Failed. " + self.run.error.splitlines()[0][:160] if self.run.error else "Failed"
        return None

    def values(self):
        return [
            duration_text(self.duration) if self.finished else None,
            self.status_text(),
            self.run.arguments or None,
        ]


def _job_context(job, days, now):
    runs_of_job = JobRun.objects.filter(job=job.name)
    first_started = runs_of_job.order_by("started_at").values_list("started_at", flat=True).first()
    if first_started is None:
        return {"empty_text": f"No runs of {job.name} are recorded yet."}
    first_day, today, tracked_from = _window(days, first_started, now)
    days_axis = TimeAxis(first_day, today, COLUMN_DAY_WIDTH, now, stretch=False)
    frequent = job.every is not None and job.every < timedelta(days=1)
    axis = TimeAxis(first_day, today, max(round(timedelta(days=1) / job.every) * RUN_WIDTH, COLUMN_DAY_WIDTH), now) if frequent else days_axis

    window_runs = list(runs_of_job.filter(started_at__gte=days_axis.start).defer("output").order_by("started_at"))
    runs = [
        _Run(run, axis.x(run.started_at), run.duration_seconds is None)
        for run in window_runs
        # One still running is left out until it ends.
        if run.duration_seconds is not None or now - run.started_at >= NEVER_FINISHED_AFTER
    ]
    by_day = {day: [] for day in days_axis.days}
    for one in runs:
        by_day[one.run.started_at.astimezone(dt_timezone.utc).date()].append(one)

    change_url = reverse("admin:jobs_jobrun_change", args=[0])
    changelist_url = reverse("admin:jobs_jobrun_changelist")
    runs_source = HoverSource("runs")
    if frequent:
        for one in runs:
            runs_source.add(one.x, moment_text(one.run.started_at), one.values(), change_url.replace("/0/", f"/{one.run.pk}/"))
    days_source = HoverSource("days")
    for day, of_day in by_day.items():
        finished = [one.duration for one in of_day if one.finished]
        failed = sum(one.failed for one in of_day)
        days_source.add(
            days_axis.day_x(day),
            day_text(day) + (", so far" if day == today else ""),
            [
                duration_text(sum(finished)) if finished else None,
                counted_text(len(of_day), "run"),
                counted_text(failed, "failed run") if failed else None,
                *(count_text(sum(one.count(key) for one in of_day)) for key, _ in job.counts),
            ],
            f"{changelist_url}?" + urlencode({
                "job": job.name, "started_at__year": day.year, "started_at__month": day.month, "started_at__day": day.day,
            }),
        )

    figures = [
        _run_time_figure(job, axis, runs, by_day, runs_source) if frequent
        else _day_time_figure(job, days_axis, by_day, days_source)
    ]
    if job.counts:
        figures.append(_counts_figure(job, days_axis, by_day, days_source))
    latest = runs_of_job.defer("counts", "output").order_by("-started_at").first()
    return {
        "range_text": _range_text(first_day, today, tracked_from, f"Runs of {job.name}"),
        "tiles": _tiles(job, runs, window_runs, latest, now, change_url, changelist_url),
        "figures": figures,
        "hover_sources": [runs_source, days_source] if frequent else [days_source],
    }


def _tiles(job, runs, window_runs, latest, now, change_url, changelist_url):
    finished = [one for one in runs if one.finished]
    failed = [one for one in runs if one.failed]
    never_finished = sum(one.never_finished for one in runs)
    missing = ""
    if job.every and window_runs:
        expected = int((now - window_runs[0].started_at - timedelta(minutes=1)) / job.every) + 1
        missing = max(expected - len(window_runs), 0)
        missing = f"{missing:,} missing" if missing else "None missing"
    tiles = [
        Tile("Runs", count_text(len(runs)), missing),
        Tile(
            "Failed",
            count_text(len(failed)),
            f"{never_finished:,} never finished" if never_finished else "",
            f"{changelist_url}?" + urlencode({"job": job.name, "status__exact": JobRun.Status.FAILED}) if failed else "",
            "critical" if failed else "",
        ),
    ]
    if finished:
        longest = max(finished, key=lambda one: one.duration)
        tiles.append(Tile(
            "Longest run", duration_text(longest.duration), moment_text(longest.run.started_at),
            change_url.replace("/0/", f"/{longest.run.pk}/"),
        ))
    late = job.every is not None and now - latest.started_at > job.every * LATE_AFTER
    tiles.append(Tile(
        "Latest run",
        _ago_text(now - latest.started_at),
        f"Overdue: it runs {every_text(job.every).lower()}" if late else _latest_note(latest, now, NEVER_FINISHED_AFTER),
        change_url.replace("/0/", f"/{latest.pk}/"),
        "warning" if late else "",
    ))
    for key, label in job.counts:
        tiles.append(Tile(label, count_text(sum(one.count(key) for one in runs))))
    return tiles


def _points(runs, value, gap):
    """(x, value) for each run, with a None wherever the line breaks: at a gap between
    runs, and at a run with no value."""
    points, previous = [], None
    for one in runs:
        if previous is not None and one.run.started_at - previous > gap:
            points.append(None)
        previous = one.run.started_at
        points.append((one.x, value(one)) if one.finished else None)
    return points


def _failed_legend(failed):
    return [LegendItem("Failed or never finished", "critical", "critical")] if failed else []


def _run_time_figure(job, axis, runs, by_day, runs_source):
    """A point for each run: a job run more often than daily."""
    longest = max((one.duration for one in runs if one.finished), default=0)
    unit, tick_text, unit_name = _time_unit(longest)
    plot = Plot(
        axis,
        label=f"Run time of each {job.name} run, in {unit_name}",
        height=238,
        max_value=longest * 1.05 / unit,
        tick_text=tick_text,
    )
    plot.add_line(_points(runs, lambda one: one.duration / unit, job.every * GAP), "series-1")
    for one in runs:
        if one.failed:
            # One that never finished has no time: its marker sits at the top.
            plot.add_marker(one.x, one.duration / unit if one.finished else plot.max_value, "critical")
    plot.hover_on(runs_source, [
        {"field": RUN_TIME, "label": "run time", "color": "series-1"},
        {"field": STATUS, "label": "", "color": None},
        {"field": ARGUMENTS, "label": "", "color": None},
    ])

    rows = []
    for day, of_day in by_day.items():
        durations = [one.duration for one in of_day if one.finished]
        rows.append([
            day_text(day),
            count_text(len(of_day)),
            duration_text(median(durations)) if durations else "-",
            duration_text(max(durations)) if durations else "-",
            count_text(sum(one.failed for one in of_day)),
        ])
    return Figure(
        key="run-time",
        title="Run time",
        subtitle=f"How long each run of {job.name} took, start to end; it runs {every_text(job.every).lower()}."
            " Failed runs are marked. Weekends are shaded.",
        plots=[plot],
        legend=_failed_legend(any(one.failed for one in runs)),
        table_headers=["Day", "Runs", "Median", "Longest", "Failed"],
        table_rows=rows,
    )


def _day_time_figure(job, days_axis, by_day, days_source):
    """A column for each day: a job run daily, or less often."""
    totals = {day: sum(one.duration for one in of_day if one.finished) for day, of_day in by_day.items()}
    unit, tick_text, unit_name = _time_unit(max(totals.values(), default=0))
    plot = Plot(
        days_axis,
        label=f"Time {job.name} ran each day, in {unit_name}",
        height=200,
        max_value=max(totals.values(), default=0) * 1.05 / unit,
        tick_text=tick_text,
    )
    plot.add_columns([(days_axis.day_x(day), [totals[day] / unit]) for day in days_axis.days], ["series-1"])
    for day, of_day in by_day.items():
        if any(one.failed for one in of_day):
            plot.add_marker(days_axis.day_x(day), totals[day] / unit, "critical")
    plot.hover_on(days_source, [
        {"field": DAY_TIME, "label": "run time", "color": "series-1"},
        {"field": DAY_RUNS, "label": "", "color": None},
        {"field": DAY_FAILED, "label": "", "color": None},
    ], crosshair=False)

    rows = []
    for day, of_day in by_day.items():
        durations = [one.duration for one in of_day if one.finished]
        rows.append([
            day_text(day),
            count_text(len(of_day)),
            duration_text(sum(durations)) if durations else "-",
            duration_text(max(durations)) if durations else "-",
            count_text(sum(one.failed for one in of_day)),
        ])
    schedule = f"it runs {every_text(job.every).lower()}" if job.every else "it's on no schedule known here"
    return Figure(
        key="run-time",
        title="Run time",
        subtitle=f"How long {job.name} ran each day, all the day's runs together; {schedule}. Days with a"
            " failed run are marked. Weekends are shaded.",
        plots=[plot],
        legend=_failed_legend(any(one.failed for of_day in by_day.values() for one in of_day)),
        table_headers=["Day", "Runs", "Time", "Longest run", "Failed"],
        table_rows=rows,
    )


def _counts_figure(job, days_axis, by_day, days_source):
    plots, totals = [], []
    for index, (key, label) in enumerate(job.counts):
        of_days = {day: sum(one.count(key) for one in of_day) for day, of_day in by_day.items()}
        totals.append(of_days)
        plot = Plot(
            days_axis,
            label=f"{label}, per day",
            title=f"{label}, per day",
            height=150,
            max_value=max(of_days.values(), default=0) * 1.05,
            integer=True,
        )
        plot.add_columns([(days_axis.day_x(day), [of_days[day]]) for day in days_axis.days], ["series-1"])
        plot.hover_on(days_source, [
            {"field": FIRST_COUNT + index, "label": label[0].lower() + label[1:], "color": "series-1"},
            {"field": DAY_RUNS, "label": "", "color": None},
        ], crosshair=False)
        plots.append(plot)

    rows = [
        [day_text(day), count_text(len(of_day)), *(count_text(of_days[day]) for of_days in totals)]
        for day, of_day in by_day.items()
    ]
    return Figure(
        key="counts",
        title="What the runs did",
        subtitle=f"What the runs of {job.name} did each day, all the day's runs together. Weekends are shaded.",
        plots=plots,
        table_headers=["Day", "Runs", *(label for _, label in job.counts)],
        table_rows=rows,
    )
