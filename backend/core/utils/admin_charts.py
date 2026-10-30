"""Charts for the admin's graph pages, drawn on the server.

A graph page builds Figures from the pieces here: a time axis of whole UTC days that
every plot on the page shares, round y-axis ticks, the SVG paths of lines and stacked
areas, columns, and the texts axes, tooltips and tables show.

The templates in templates/admin/charts draw them. A plot is at least its days times
the axis' day_width pixels wide: a wider screen stretches it, a narrower one scrolls
it. Lines and areas are SVG stretched across the plot; labels, markers and columns are
laid over it in HTML, so they keep their size, and the y-axis and end labels sit in
columns beside it, so they stay in view. The page's script adds the hover tooltip and
scrolls the plots together. GraphsAdminMixin puts such a page beside a ModelAdmin's list.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import NamedTuple

from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path

# The room above a plot's top gridline, and under its base for each row of x-axis labels.
TOP = 12
LABEL_ROW = 18

# The pages' time ranges, in days, and the one a page opens with.
WINDOWS = (7, 14, 30)
DEFAULT_WINDOW = 14

# A day this wide gets the hours every HOUR_LABEL_STEP, and its name on a row of its
# own under them; a narrower one just its short name under its middle, as "We 28", on
# every day or every few days, so that the names stay MIN_DAY_LABEL_GAP apart: a name
# takes about 35 pixels, and fonts differ.
MIN_HOURS_DAY_WIDTH = 240
HOUR_LABEL_STEP = 6
MIN_DAY_LABEL_GAP = 48

# Days of one column each are just wide enough to name every column, and the columns
# as wide as their days but for COLUMN_GAP between them.
COLUMN_DAY_WIDTH = MIN_DAY_LABEL_GAP
COLUMN_GAP = 8

# End labels closer than this would overlap; the lower one is left to the legend.
MIN_END_LABEL_GAP = 14

# The gap between the stacked parts of a column.
STACK_GAP = 2


def window_days(raw):
    """A page's ?days=, as one of WINDOWS; DEFAULT_WINDOW for anything else."""
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW
    return days if days in WINDOWS else DEFAULT_WINDOW


def nice_ticks(top, count=4, integer=False):
    """Round values from 0 to just past top, about count steps: (values, the axis' top)."""
    top = top if top > 0 else 1
    raw_step = top / count
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if integer and step != int(step):
            continue
        if step >= raw_step:
            break
    if integer:
        step = max(step, 1)
    steps = math.ceil(top / step - 1e-9)
    return [round(index * step, 9) for index in range(steps + 1)], steps * step


def duration_text(seconds):
    """45 -> "45s", 369 -> "6m 09s", 3720 -> "1h 02m"."""
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def count_text(value):
    return f"{round(value):,}"


def counted_text(value, noun):
    """1 -> "1 run", 72 -> "72 runs"."""
    return f"{value:,} {noun}{'' if value == 1 else 's'}"


def compact_text(value):
    """Axis-tick numbers: 0, 500, 2.5K, 20K, 1.2M."""
    for size, suffix in ((1_000_000, "M"), (1000, "K")):
        if abs(value) >= size:
            return f"{round(value / size, 2):g}{suffix}"
    return f"{value:g}"


def day_text(day):
    return f"{day:%a} {day.day} {day:%b}"


def moment_text(moment):
    moment = moment.astimezone(dt_timezone.utc)
    return f"{day_text(moment)}, {moment:%H:%M} UTC"


def _number(value):
    """A coordinate as the SVG gets it: one decimal at most."""
    return f"{round(value, 1):g}"


class Tick(NamedTuple):
    at: float
    label: str


class XLabel(NamedTuple):
    left: float  # percent of the plot's width
    text: str
    kind: str  # day (at a day's start), hour, or middle (under a day's middle)
    width: float = 0  # a day label's: its day's width, as a percent, which it stays inside


class Band(NamedTuple):
    x: float
    width: float


class Label(NamedTuple):
    y: float
    text: str


class Mark(NamedTuple):
    path: str
    color: str


class Marker(NamedTuple):
    left: float  # percent of the plot's width
    y: float
    kind: str


class ColumnPart(NamedTuple):
    top: float
    height: float
    color: str
    rounded: bool


class Column(NamedTuple):
    index: int
    left: float  # percent of the plot's width
    parts: list


class TimeAxis:
    """Whole UTC days, first_day to last_day, day_width pixels each: at the least when
    the axis stretches to the page's width, exactly when it doesn't, as for columns of
    one value a day, which then stand close together. Plots on one axis scroll together."""

    def __init__(self, first_day, last_day, day_width, now, stretch=True):
        self.days = [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]
        self.start = datetime.combine(first_day, time(), tzinfo=dt_timezone.utc)
        self.end = self.start + timedelta(days=len(self.days))
        self.day_width = day_width
        self.width = day_width * len(self.days)
        self.stretch = stretch
        self.now = self.x(min(max(now, self.start), self.end))

    def x(self, moment):
        return round((moment - self.start) / (self.end - self.start) * self.width, 1)

    def day_x(self, day):
        """The middle of a day, where its column stands."""
        return self.x(datetime.combine(day, time(12), tzinfo=dt_timezone.utc))

    def percent(self, x):
        """How far across the plot x is, for what's laid over it in HTML."""
        return round(x / self.width * 100, 3)

    @property
    def label_rows(self):
        return 2 if self.day_width >= MIN_HOURS_DAY_WIDTH else 1

    def labels(self):
        if self.label_rows == 2:
            labels = []
            for index, day in enumerate(self.days):
                labels.append(XLabel(
                    self.percent(index * self.day_width), f"{day:%a} {day.day}", "day", self.percent(self.day_width),
                ))
                for hour in range(HOUR_LABEL_STEP, 24, HOUR_LABEL_STEP):
                    labels.append(XLabel(self.percent((index + hour / 24) * self.day_width), f"{hour:02d}:00", "hour"))
            return labels
        every = math.ceil(MIN_DAY_LABEL_GAP / self.day_width)
        return [XLabel(self.percent(self.day_x(day)), f"{day:%a}"[:2] + f" {day.day}", "middle") for day in self.days[::every]]

    def midnights(self):
        """Where one day ends and the next starts."""
        return [round(index * self.day_width, 1) for index in range(1, len(self.days))]

    def weekends(self):
        return [Band(round(index * self.day_width, 1), self.day_width) for index, day in enumerate(self.days) if day.weekday() >= 5]


def _stretches(points):
    """The runs of points between gaps, a gap being a None."""
    stretch = []
    for point in points:
        if point is None:
            if stretch:
                yield stretch
            stretch = []
        else:
            stretch.append(point)
    if stretch:
        yield stretch


def line_path(points):
    """An SVG path through (x, y) points. A None breaks the line, so missing data shows
    as a gap rather than a line drawn across it; a lone point still shows, as a dot."""
    return "".join(
        "M" + "L".join(f"{_number(x)},{_number(y)}" for x, y in (stretch if len(stretch) > 1 else stretch * 2))
        for stretch in _stretches(points)
    )


def band_path(points):
    """An SVG path filling between two edges, from (x, lower y, upper y) points; None
    breaks it, as in line_path."""
    paths = []
    for stretch in _stretches(points):
        stretch = stretch if len(stretch) > 1 else stretch * 2
        upper = "L".join(f"{_number(x)},{_number(upper)}" for x, _, upper in stretch)
        lower = "L".join(f"{_number(x)},{_number(lower)}" for x, lower, _ in reversed(stretch))
        paths.append(f"M{upper}L{lower}Z")
    return "".join(paths)


class Plot:
    """One plot on a page's time axis: what templates/admin/charts/plot.html draws.

    Values come in as (x, value) points, None for a gap; the plot turns them into
    paths on its own y scale, which runs from 0 to a round number past max_value.
    """

    top = TOP

    def __init__(self, axis, *, label, height, max_value, title="", tick_text=compact_text, integer=False):
        self.axis = axis
        self.width = axis.width
        self.stretch = axis.stretch
        self.group = f"axis-{id(axis)}"
        self.now_percent = axis.percent(axis.now)
        self.label = label
        self.title = title
        self.height = height
        self.base = height - 10 - LABEL_ROW * axis.label_rows
        self.inner_height = self.base - TOP
        self.x_label_top = self.base + 6
        self.day_label_top = self.x_label_top + LABEL_ROW
        values, self.max_value = nice_ticks(max_value, integer=integer)
        self.y_ticks = [Tick(self.y(value), tick_text(value)) for value in values]
        self.x_labels = axis.labels()
        # Lines between wide days cross the plot; between narrow ones, as under columns,
        # they only part the days' names, down to the names' bottom.
        self.midnights, self.separators = (axis.midnights(), []) if axis.label_rows == 2 else ([], axis.midnights())
        self.separator_bottom = self.x_label_top + 16
        self.weekends = axis.weekends()
        self.column_width = axis.day_width - COLUMN_GAP
        self.areas, self.lines, self.columns = [], [], []
        self.references, self.markers, self.labels = [], [], []
        self.hover = ""
        self.fields_json = "[]"
        self.crosshair = False

    def y(self, value):
        return round(self.base - min(max(value, 0), self.max_value) / self.max_value * self.inner_height, 1)

    def add_line(self, points, color, end_label=""):
        self.lines.append(Mark(line_path([point and (point[0], self.y(point[1])) for point in points]), color))
        if end_label:
            last = next((point for point in reversed(points) if point is not None), None)
            if last is not None:
                self._end_labels([(self.y(last[1]), end_label)])

    def add_stack(self, points, layers):
        """Stacked areas: points carry one value per layer, bottom first, and layers one
        (color, end label) each. Each area's top edge is drawn as a line too."""
        totals = [point and (point[0], [sum(point[1][:index]) for index in range(len(layers) + 1)]) for point in points]
        labels = []
        for index, (color, end_label) in enumerate(layers):
            edges = [total and (total[0], self.y(total[1][index]), self.y(total[1][index + 1])) for total in totals]
            self.areas.append(Mark(band_path(edges), color))
            self.lines.append(Mark(line_path([edge and (edge[0], edge[2]) for edge in edges]), color))
            last = next((edge for edge in reversed(edges) if edge is not None), None)
            if last is not None and last[1] - last[2] >= MIN_END_LABEL_GAP:
                labels.append(((last[1] + last[2]) / 2, end_label))
        self._end_labels(labels)

    def add_columns(self, points, colors):
        """Columns at days' middles, stacked from points of one value per color, bottom
        first, with a gap between the parts; only the top part is rounded."""
        for index, point in enumerate(points):
            if point is None:
                continue
            x, values = point
            parts, total = [], 0
            top_part = max((part for part, value in enumerate(values) if value > 0), default=None)
            for part, (value, color) in enumerate(zip(values, colors)):
                if value <= 0:
                    continue
                base_y = self.y(total) - (STACK_GAP if total > 0 else 0)
                total += value
                top_y = self.y(total)
                if base_y - top_y > 0:
                    parts.append(ColumnPart(top_y, round(base_y - top_y, 1), color, part == top_part))
            self.columns.append(Column(index, self.axis.percent(x), parts))

    def add_reference(self, value, label):
        self.references.append(Label(self.y(value), label))

    def add_marker(self, x, value, kind):
        self.markers.append(Marker(self.axis.percent(x), self.y(value), kind))

    def hover_on(self, source, fields, crosshair=True):
        """Give the plot a tooltip from a page's HoverSource, listing the given fields:
        dicts of field (the index in each row's values), label, and color."""
        self.hover = source.key
        self.fields_json = json.dumps(fields)
        self.crosshair = crosshair

    def _end_labels(self, candidates):
        placed = [label.y for label in self.labels] + [reference.y for reference in self.references]
        for y, text in sorted(candidates):
            if any(abs(y - other) < MIN_END_LABEL_GAP for other in placed):
                continue
            placed.append(y)
            self.labels.append(Label(round(y, 1), text))


@dataclass
class HoverSource:
    """The rows a page's tooltips read, one per x position: a title, the values as
    texts (None where there's nothing to show), and where a click goes."""

    key: str
    xs: list = field(default_factory=list)
    rows: list = field(default_factory=list)

    @property
    def element_id(self):
        return f"viz-source-{self.key}"

    @property
    def data(self):
        return {"xs": self.xs, "rows": self.rows}

    def add(self, x, title, values, url=None):
        self.xs.append(x)
        self.rows.append({"title": title, "values": values, "url": url})


class LegendItem(NamedTuple):
    label: str
    color: str
    shape: str  # line, rect, critical or warning


@dataclass
class Figure:
    """A chart: its heading, what it shows, a legend, one plot or several small ones,
    and the table that holds the same numbers."""

    key: str
    title: str
    subtitle: str
    plots: list
    legend: list = field(default_factory=list)
    table_headers: list = field(default_factory=list)
    table_rows: list = field(default_factory=list)


class Tile(NamedTuple):
    label: str
    value: str
    note: str = ""
    url: str = ""
    marker: str = ""


class GraphsAdminMixin:
    """A Graphs page for a ModelAdmin, at graphs/ under its changelist, which links to it.

    graphs_context(request, days) builds the page's context: range_text, tiles, figures
    and hover_sources, or just empty_text while there's nothing to show. It may add a
    select, a dict of name, label and options (each a value, label and selected), shown
    beside the time ranges and kept as they change.
    """

    change_list_template = "admin/charts/change_list.html"
    graphs_title = "Graphs"

    def graphs_context(self, request, days):
        raise NotImplementedError

    def get_urls(self):
        name = f"{self.opts.app_label}_{self.opts.model_name}_graphs"
        # Ahead of the ModelAdmin's own, whose <object_id>/ would take graphs/ for an id.
        return [path("graphs/", self.admin_site.admin_view(self.graphs_view), name=name), *super().get_urls()]

    def graphs_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        days = window_days(request.GET.get("days"))
        windows = []
        for one in WINDOWS:
            params = request.GET.copy()
            params["days"] = one
            windows.append({"label": f"Last {one} days", "href": f"?{params.urlencode()}", "selected": one == days})
        return TemplateResponse(request, "admin/charts/page.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": self.graphs_title,
            "days": days,
            "windows": windows,
            **self.graphs_context(request, days),
        })
