"""The admin's Fetch runs > Graphs page: how long each fetch_twitch_streams run took,
where the time went, how hard it used Helix, and what it collected, for all the
languages together or one of them."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta, timezone as dt_timezone
from functools import cached_property
from statistics import mean, median

from django.urls import reverse
from django.utils import timezone

from apps.fetch.models import FetchRun
from apps.streams.search import StreamerSearch
from core.utils.admin_charts import (
    COLUMN_DAY_WIDTH,
    Figure,
    HoverSource,
    LegendItem,
    Plot,
    Tile,
    TimeAxis,
    compact_text,
    count_text,
    counted_text,
    day_text,
    duration_text,
    moment_text,
)

# fetch_twitch_streams' own settings, set in its handle(): the time limit on polling,
# and the shortest a language's poll round lasts, which keeps it under the Helix limit.
TIME_LIMIT_SECONDS = 900
MIN_ROUND_SECONDS = 20

# Twitch's Helix rate limit for an app token, shared by the languages polling at once.
HELIX_REQUESTS_PER_MINUTE = 800

# The crontab starts a run at :00, :20 and :40. Runs further apart than GAP have runs
# missing between them, and the lines break there.
RUN_INTERVAL = timedelta(minutes=20)
GAP = timedelta(minutes=45)

# A run still RUNNING this long after it started was killed rather than slow: the time
# limit ends its polling at 15 minutes.
NEVER_FINISHED_AFTER = timedelta(hours=1)

# Each day is drawn at least this wide: 10 pixels a run, at three runs an hour. The
# plots of one column a day have narrower days of their own, COLUMN_DAY_WIDTH.
DAY_WIDTH = 720

# The values of a run's tooltip row, and of a day's, in this order.
RUN_TIME, STATUS, WRITING, HELIX, FINALIZING, OTHER, BUSIEST, AVERAGE, WRITTEN, KEPT, DROPPED = range(11)
NEW_STREAMS, NEW_STREAMERS, RUNS = range(3)

# What polling's time is spent on, bottom of the stack first: (key, color, label).
TIME_PARTS = (
    ("writing", "series-1", "Writing streams"),
    ("helix", "series-2", "Waiting on Helix"),
    ("finalizing", "series-3", "Finalizing"),
    ("other", "other", "Other"),
)
TIME_PART_FIELDS = {"writing": WRITING, "helix": HELIX, "finalizing": FINALIZING, "other": OTHER}


def time_parts(language):
    """Finalizing the ended streams comes after the languages' polling, for the whole
    run, so a language's own time has no part of it."""
    return [part for part in TIME_PARTS if not (language and part[0] == "finalizing")]


def busiest_minute(languages):
    """The most Helix requests a run sent in any 60 seconds, estimated from its rounds.

    The languages poll side by side from the run's start. A language's rounds follow
    one another, none shorter than MIN_ROUND_SECONDS, and a round's requests are spread
    evenly over its time waiting on Helix. The busiest minute starts or ends where a
    round's Helix time does, so only those moments are tried.
    """
    spans = []
    for language in languages:
        start = 0.0
        for one_round in language.rounds_detail:
            helix_seconds = one_round["helix_seconds"]
            spans.append((start, start + helix_seconds, one_round["requests"]))
            start += max(helix_seconds + one_round["write_seconds"], MIN_ROUND_SECONDS)

    def sent_in_minute_from(moment):
        sent = 0.0
        for span_start, span_end, requests in spans:
            if span_end <= span_start:
                sent += requests if moment <= span_start < moment + 60 else 0
                continue
            overlap = min(span_end, moment + 60) - max(span_start, moment)
            if overlap > 0:
                sent += requests * overlap / (span_end - span_start)
        return sent

    moments = {edge - offset for span_start, span_end, _ in spans for edge in (span_start, span_end) for offset in (0, 60)}
    return max((sent_in_minute_from(moment) for moment in moments), default=0.0)


@dataclass
class _Run:
    """A run as the page shows it: all its languages together, or just one of them."""

    run: FetchRun
    x: float
    languages: list = field(default_factory=list)
    never_finished: bool = False
    language: str = ""

    @cached_property
    def polled(self):
        """The language rows shown: all of them, or the chosen language's."""
        if not self.language:
            return self.languages
        return [one for one in self.languages if one.language == self.language]

    @property
    def finished(self):
        if self.run.duration_seconds is None or not self.polled:
            return False
        return not self.language or self.polled[0].duration_seconds is not None

    @property
    def duration(self):
        """The run's time, start to end, or the chosen language's polling time."""
        return self.polled[0].duration_seconds if self.language else self.run.duration_seconds

    @property
    def failed(self):
        if self.never_finished:
            return True
        if self.language:
            return any(one.error for one in self.polled)
        return self.run.status == FetchRun.Status.FAILED

    @property
    def time_limit_hit(self):
        if self.language:
            return any(one.time_limit_hit for one in self.polled)
        return self.run.time_limit_hit

    @cached_property
    def slowest(self):
        return max(self.polled, key=lambda language: language.duration_seconds or 0, default=None)

    @cached_property
    def time_split(self):
        """The time in time_parts() order: the slowest language, or the chosen one,
        writing streams and waiting on Helix; for the whole run, finalizing ended
        streams after that; then the rest."""
        writing = self.slowest.write_seconds if self.slowest else 0
        helix = self.slowest.helix_seconds if self.slowest else 0
        if self.language:
            return [writing, helix, max(self.duration - writing - helix, 0)]
        finalizing = self.run.finalize_seconds or 0
        return [writing, helix, finalizing, max(self.duration - writing - helix - finalizing, 0)]

    @cached_property
    def busiest_minute(self):
        return busiest_minute(self.polled)

    @cached_property
    def average_per_minute(self):
        """Helix requests a minute over the polling, which ends with its slowest language.
        Polling shorter than a minute counts as a minute, or the average would come out
        higher than the busiest minute."""
        if not self.slowest or not self.slowest.duration_seconds:
            return None
        return sum(language.requests for language in self.polled) / (max(self.slowest.duration_seconds, 60) / 60)

    @property
    def written(self):
        return sum(language.streams_written for language in self.polled)

    def status_text(self):
        if self.never_finished:
            return "Never finished: the run is still marked running"
        if self.failed:
            errors = ([] if self.language else [self.run.error]) + [
                f"{one.language}: {one.error}" for one in self.polled if one.error
            ]
            return "Failed. " + "; ".join(error.splitlines()[0][:160] for error in errors if error)
        if self.time_limit_hit:
            return "Stopped at the time limit"
        return None

    def values(self):
        if not self.finished:
            return [None, self.status_text()] + [None] * 9
        parts = {key: duration_text(part) for (key, _, _), part in zip(time_parts(self.language), self.time_split)}
        return [
            duration_text(self.duration),
            self.status_text(),
            *(parts.get(key) for key in TIME_PART_FIELDS),
            f"{self.busiest_minute:,.0f}/min",
            None if self.average_per_minute is None else f"{self.average_per_minute:,.0f}/min",
            count_text(self.written),
            count_text(self.run.streams_finalized),
            count_text(self.run.streams_dropped),
        ]


def _points(runs, value):
    """(x, value) for each run, with a None wherever the line breaks: at a gap between
    runs, and at a run with no value."""
    points, previous = [], None
    for one in runs:
        if previous is not None and one.run.started_at - previous > GAP:
            points.append(None)
        previous = one.run.started_at
        result = value(one) if one.finished else None
        points.append(None if result is None else (one.x, result))
    return points


def _minutes_tick(minutes):
    return "0" if minutes == 0 else f"{minutes:g} min"


def _languages(runs):
    """The languages these runs polled, most streams first: {code: name}."""
    written = Counter()
    for run in runs:
        for language in run.languages.all():
            written[language.language] += language.streams_written
    return {code: StreamerSearch.language_label(code) for code, _ in written.most_common()}


def fetch_graphs(days, language="", now=None):
    """The Fetch runs > Graphs page's context, for the last `days` days, and for all
    languages or just `language`."""
    now = now or timezone.now()
    context = {"empty_text": "No fetch runs are recorded yet."}
    first_started = FetchRun.objects.order_by("started_at").values_list("started_at", flat=True).first()
    if first_started is None:
        return context

    today = now.astimezone(dt_timezone.utc).date()
    tracked_from = first_started.astimezone(dt_timezone.utc).date()
    first_day = max(today - timedelta(days=days - 1), tracked_from)
    axis = TimeAxis(first_day, today, DAY_WIDTH, now)
    days_axis = TimeAxis(first_day, today, COLUMN_DAY_WIDTH, now, stretch=False)
    window_runs = list(FetchRun.objects.filter(started_at__gte=axis.start).prefetch_related("languages").order_by("started_at"))
    languages = _languages(window_runs)
    if language not in languages:
        language = ""
    name = languages.get(language, "")
    runs = [
        _Run(run, axis.x(run.started_at), list(run.languages.all()), run.duration_seconds is None, language)
        for run in window_runs
        # One still running is left out until it ends.
        if run.duration_seconds is not None or now - run.started_at >= NEVER_FINISHED_AFTER
    ]
    by_day = {day: [] for day in axis.days}
    for one in runs:
        by_day[one.run.started_at.astimezone(dt_timezone.utc).date()].append(one)

    change_url = reverse("admin:fetch_fetchrun_change", args=[0])
    runs_source = HoverSource("runs")
    for one in runs:
        runs_source.add(one.x, moment_text(one.run.started_at), one.values(), change_url.replace("/0/", f"/{one.run.pk}/"))

    changelist_url = reverse("admin:fetch_fetchrun_changelist")
    days_source = HoverSource("days")
    new_streams = {day: sum(row.streams_created for one in by_day[day] for row in one.polled) for day in axis.days}
    new_streamers = {day: sum(row.profiles_created for one in by_day[day] for row in one.polled) for day in axis.days}
    for day in axis.days:
        days_source.add(
            days_axis.day_x(day),
            day_text(day) + (", so far" if day == today else ""),
            [count_text(new_streams[day]), count_text(new_streamers[day]), counted_text(len(by_day[day]), "run")],
            f"{changelist_url}?started_at__year={day.year}&started_at__month={day.month}&started_at__day={day.day}",
        )

    range_text = f"{day_text(axis.days[0])} to {day_text(axis.days[-1])}, UTC"
    if axis.days[0] == tracked_from:
        range_text += f". Runs are recorded from {day_text(tracked_from)}."
    context.update({
        "select": {
            "name": "lang",
            "label": "Language",
            "options": [{"value": "", "label": "All languages", "selected": not language}] + [
                {"value": code, "label": f"{label} ({code})" if label != code else code, "selected": code == language}
                for code, label in languages.items()
            ],
        },
        "range_text": range_text,
        "tiles": _tiles(runs, window_runs, now, change_url, changelist_url, language),
        "figures": [
            _run_time_figure(axis, runs, by_day, runs_source, name),
            _time_split_figure(axis, runs, by_day, runs_source, language, name),
            _helix_figure(axis, runs, by_day, runs_source, name),
            _collected_figure(axis, days_axis, runs, by_day, runs_source, days_source, new_streams, new_streamers, language),
        ],
        "hover_sources": [runs_source, days_source],
    })
    return context


def _tiles(runs, window_runs, now, change_url, changelist_url, language):
    finished = [one for one in runs if one.finished]
    failed = [one for one in runs if one.failed]
    never_finished = sum(one.never_finished for one in runs)
    limit_hits = sum(one.time_limit_hit for one in runs)
    tiles = []

    if window_runs:
        expected = int((now - window_runs[0].started_at - timedelta(minutes=1)) / RUN_INTERVAL) + 1
        missing = max(expected - len(window_runs), 0)
        tiles.append(Tile("Runs", count_text(len(runs)), f"{missing:,} missing" if missing else "None missing"))
    tiles.append(Tile(
        "Failed",
        count_text(len(failed)),
        f"{never_finished:,} never finished" if never_finished else "",
        f"{changelist_url}?status__exact={FetchRun.Status.FAILED}" if failed and not language else "",
        "critical" if failed else "",
    ))
    tiles.append(Tile(
        "Stopped at the time limit", count_text(limit_hits), "15-minute limit", "", "warning" if limit_hits else "",
    ))
    if finished:
        longest = max(finished, key=lambda one: one.duration)
        tiles.append(Tile(
            f"Longest {language} polling" if language else "Longest run",
            duration_text(longest.duration),
            moment_text(longest.run.started_at),
            change_url.replace("/0/", f"/{longest.run.pk}/"),
        ))
    if window_runs:
        latest = window_runs[-1]
        minutes_ago = round((now - latest.started_at).total_seconds() / 60)
        if latest.duration_seconds is not None:
            note = f"{latest.get_status_display()}, {duration_text(latest.duration_seconds)}"
        elif now - latest.started_at < NEVER_FINISHED_AFTER:
            note = "Running now"
        else:
            note = "Never finished"
        overdue = now - latest.started_at > RUN_INTERVAL + timedelta(minutes=5)
        tiles.append(Tile(
            "Latest run",
            f"{minutes_ago:,} min ago",
            "Overdue: runs start every 20 minutes" if overdue else note,
            change_url.replace("/0/", f"/{latest.pk}/"),
            "warning" if overdue else "",
        ))
    return tiles


def _add_limit(plot, value, label):
    """A limit's line, when the plot reaches up to it. A language's own plots are scaled
    to its numbers, which may sit far below a limit every language shares."""
    if value <= plot.max_value:
        plot.add_reference(value, label)


def _run_time_figure(axis, runs, by_day, runs_source, name):
    longest = max((one.duration for one in runs if one.finished), default=0)
    plot = Plot(
        axis,
        label=f"Polling time of the {name} streams in each run, in minutes" if name
            else "Run time of each fetch run, in minutes",
        height=258,
        max_value=(longest if name else max(longest, TIME_LIMIT_SECONDS)) * 1.05 / 60,
        tick_text=_minutes_tick,
    )
    _add_limit(plot, TIME_LIMIT_SECONDS / 60, "Time limit, 15 min")
    plot.add_line(_points(runs, lambda one: one.duration / 60), "series-1")
    for one in runs:
        if one.failed:
            plot.add_marker(one.x, (one.duration if one.finished else TIME_LIMIT_SECONDS) / 60, "critical")
        elif one.time_limit_hit:
            plot.add_marker(one.x, one.duration / 60, "warning")
    plot.hover_on(runs_source, [
        {"field": RUN_TIME, "label": "polling time" if name else "run time", "color": "series-1"},
        {"field": STATUS, "label": "", "color": None},
    ])

    legend = []
    if any(one.failed for one in runs):
        legend.append(LegendItem("Failed or never finished", "critical", "critical"))
    if any(one.time_limit_hit and not one.failed for one in runs):
        legend.append(LegendItem("Stopped at the time limit", "warning", "warning"))

    rows = []
    for day, of_day in by_day.items():
        durations = [one.duration for one in of_day if one.finished]
        rows.append([
            day_text(day),
            count_text(len(of_day)),
            duration_text(median(durations)) if durations else "-",
            duration_text(max(durations)) if durations else "-",
            count_text(sum(one.time_limit_hit for one in of_day)),
            count_text(sum(one.failed for one in of_day)),
        ])
    if name:
        subtitle = (
            f"How long polling the {name} streams took in each run; the run's own time includes it. At 15"
            " minutes polling stops, and the pages it didn't reach are skipped until the next run; the line"
            " shows when the plot reaches that high. Weekends are shaded."
        )
    else:
        subtitle = (
            "How long each run took, start to end. At 15 minutes a run stops polling, and the pages it didn't"
            " reach are skipped until the next run. Weekends are shaded."
        )
    return Figure(
        key="run-time",
        title=f"Polling time, {name}" if name else "Run time",
        subtitle=subtitle,
        plots=[plot],
        legend=legend,
        table_headers=["Day", "Runs", "Median", "Longest", "Stopped at the limit", "Failed"],
        table_rows=rows,
    )


def _time_split_figure(axis, runs, by_day, runs_source, language, name):
    parts = time_parts(language)
    longest = max((one.duration for one in runs if one.finished), default=0)
    plot = Plot(
        axis,
        label=f"The {name} polling time split into writing streams, waiting on Helix and the rest" if name
            else "Each run's time split into writing streams, waiting on Helix, finalizing and the rest",
        height=258,
        max_value=longest * 1.05 / 60,
        tick_text=_minutes_tick,
    )
    plot.add_stack(_points(runs, lambda one: [part / 60 for part in one.time_split]), [(color, label) for _, color, label in parts])
    plot.hover_on(runs_source, [
        {"field": TIME_PART_FIELDS[key], "label": label.lower().replace("helix", "Helix"), "color": color}
        for key, color, label in parts
    ] + [{"field": RUN_TIME, "label": "polling time" if name else "run time", "color": None}])

    rows = []
    for day, of_day in by_day.items():
        splits = [one.time_split for one in of_day if one.finished]
        rows.append([day_text(day)] + [
            duration_text(mean(split[index] for split in splits)) if splits else "-" for index in range(len(parts))
        ])
    if name:
        subtitle = (
            f"Polling the {name} streams: writing them to the database and waiting on Helix. Other is sleeping"
            " between rounds and the rest. The top of the stack is the polling time; finalizing the streams"
            " that ended comes after it, for the whole run."
        )
    else:
        subtitle = (
            "The run's slowest language (en, in practice) writing its streams to the database and waiting on"
            " Helix, then finalizing the streams that ended. Other is sleeping between rounds and the rest."
            " The top of the stack is the run time."
        )
    return Figure(
        key="time-split",
        title=f"Where the {name} polling time goes" if name else "Where a run's time goes",
        subtitle=subtitle,
        plots=[plot],
        legend=[LegendItem(label, color, "rect") for _, color, label in parts],
        table_headers=["Day"] + [f"{label}, average" for _, _, label in parts],
        table_rows=rows,
    )


def _helix_figure(axis, runs, by_day, runs_source, name):
    busiest = max((one.busiest_minute for one in runs if one.finished), default=0)
    plot = Plot(
        axis,
        label="Helix requests in each run's busiest minute and on average, against the limit of 800 a minute",
        height=238,
        max_value=(busiest if name else max(busiest, HELIX_REQUESTS_PER_MINUTE)) * 1.05,
        tick_text=compact_text,
    )
    _add_limit(plot, HELIX_REQUESTS_PER_MINUTE, "Limit, 800/min")
    plot.add_line(_points(runs, lambda one: one.busiest_minute), "series-1", end_label="Busiest minute")
    plot.add_line(_points(runs, lambda one: one.average_per_minute), "series-2", end_label="Average")
    plot.hover_on(runs_source, [
        {"field": BUSIEST, "label": "busiest minute", "color": "series-1"},
        {"field": AVERAGE, "label": "average", "color": "series-2"},
    ])

    rows = []
    for day, of_day in by_day.items():
        finished = [one for one in of_day if one.finished]
        averages = [one.average_per_minute for one in finished if one.average_per_minute is not None]
        rows.append([
            day_text(day),
            f"{max(one.busiest_minute for one in finished):,.0f}/min" if finished else "-",
            f"{mean(averages):,.0f}/min" if averages else "-",
            count_text(sum(row.requests for one in of_day for row in one.polled)),
        ])
    if name:
        subtitle = (
            f"The Helix requests for the {name} streams alone: the busiest minute in each run, estimated from"
            " the rounds' timings, and the average over the polling. The limit of 800 requests a minute is"
            " shared by every language polling at the time, so it's drawn only if the plot reaches it."
        )
    else:
        subtitle = (
            "Each run's busiest minute, estimated from its rounds' timings, and its average over the polling,"
            " against Twitch's limit of 800 requests a minute."
        )
    return Figure(
        key="helix",
        title="Helix requests per minute",
        subtitle=subtitle,
        plots=[plot],
        legend=[LegendItem("Busiest minute", "series-1", "line"), LegendItem("Average", "series-2", "line")],
        table_headers=["Day", "Busiest minute", "Average", "Requests"],
        table_rows=rows,
    )


def _collected_figure(axis, days_axis, runs, by_day, runs_source, days_source, new_streams, new_streamers, language):
    # Finalizing is the run's, not a language's, so those two always count every language.
    all_languages = " (all languages)" if language else ""
    plots = []
    for title, value, field_index in (
        ("Streams written, per run", lambda one: one.written, WRITTEN),
        (f"Ended streams kept, per run{all_languages}", lambda one: one.run.streams_finalized, KEPT),
        (f"Ended streams dropped for too little data, per run{all_languages}", lambda one: one.run.streams_dropped, DROPPED),
    ):
        plot = Plot(
            axis,
            label=title,
            title=title,
            height=168,
            max_value=max((value(one) for one in runs if one.finished), default=0) * 1.05,
        )
        plot.add_line(_points(runs, value), "series-1")
        plot.hover_on(runs_source, [{"field": field_index, "label": title.split(",")[0].lower(), "color": "series-1"}])
        plots.append(plot)

    for title, totals, field_index in (
        ("New streams per day", new_streams, NEW_STREAMS),
        ("New streamers per day", new_streamers, NEW_STREAMERS),
    ):
        plot = Plot(days_axis, label=title, title=title, height=150, max_value=max(totals.values(), default=0) * 1.05, integer=True)
        plot.add_columns([(days_axis.day_x(day), [totals[day]]) for day in days_axis.days], ["series-1"])
        plot.hover_on(days_source, [
            {"field": field_index, "label": title.lower().replace(" per day", ""), "color": "series-1"},
            {"field": RUNS, "label": "", "color": None},
        ], crosshair=False)
        plots.append(plot)

    rows = []
    for day, of_day in by_day.items():
        rows.append([
            day_text(day),
            count_text(sum(one.written for one in of_day)),
            count_text(sum(one.run.streams_finalized for one in of_day)),
            count_text(sum(one.run.streams_dropped for one in of_day)),
            count_text(new_streams[day]),
            count_text(new_streamers[day]),
        ])
    return Figure(
        key="collected",
        title="What the runs collected",
        subtitle="Streams written in each run, new and already live, and the ended streams it finalized: kept,"
            " or dropped for one snapshot or under 3 viewers. Then the streams and streamers seen for the first"
            " time, per day.",
        plots=plots,
        table_headers=["Day", "Streams written", "Ended and kept", "Ended and dropped", "New streams", "New streamers"],
        table_rows=rows,
    )
