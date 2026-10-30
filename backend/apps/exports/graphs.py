"""The admin's Exports > Graphs page: exports per day, and how many repeat one the same
user made on an earlier day, the sign of someone coming back for fresher numbers."""

import json
from datetime import timedelta, timezone as dt_timezone

from django.urls import reverse
from django.utils import timezone

from apps.exports.models import Export
from core.utils.admin_charts import (
    COLUMN_DAY_WIDTH,
    Figure,
    HoverSource,
    LegendItem,
    Plot,
    Tile,
    TimeAxis,
    count_text,
    counted_text,
    day_text,
)

# The values of a day's tooltip row, in this order.
EXPORTS, AGAIN, FIRST, USERS = range(4)

# A day's column, bottom first: (color, label).
PARTS = (("series-1", "Exported again"), ("other", "First export"))


def _export_key(export):
    """What makes two exports the same one: the same user exporting the same list, or
    the same search. A list's export whose list is gone since matches no other."""
    if export["source"] == Export.Source.LIST:
        target = export["list_of_streamers_id"] or f"deleted list, export {export['id']}"
    else:
        target = json.dumps(export["search_filters"], sort_keys=True)
    return export["user_id"], export["source"], target


def export_graphs(days, now=None):
    """The Exports > Graphs page's context, for the last `days` days."""
    now = now or timezone.now()
    context = {"empty_text": "No exports are recorded yet."}
    exports = list(Export.objects.order_by("created_at").values(
        "id", "user_id", "source", "list_of_streamers_id", "search_filters", "created_at",
    ))
    if not exports:
        return context

    # Read from the first export on, so one made again is told apart even when the
    # first time was before the window.
    first_day_of = {}
    for export in exports:
        export["day"] = export["created_at"].astimezone(dt_timezone.utc).date()
        export["again"] = first_day_of.setdefault(_export_key(export), export["day"]) < export["day"]

    today = now.astimezone(dt_timezone.utc).date()
    recorded_from = exports[0]["day"]
    axis = TimeAxis(max(today - timedelta(days=days - 1), recorded_from), today, COLUMN_DAY_WIDTH, now, stretch=False)
    by_day = {day: [] for day in axis.days}
    for export in exports:
        if export["day"] in by_day:
            by_day[export["day"]].append(export)
    in_window = [export for of_day in by_day.values() for export in of_day]

    changelist_url = reverse("admin:exports_export_changelist")
    source = HoverSource("days")
    columns, rows = [], []
    for day, of_day in by_day.items():
        again = sum(export["again"] for export in of_day)
        values = [len(of_day), again, len(of_day) - again, len({export["user_id"] for export in of_day})]
        source.add(
            axis.day_x(day),
            day_text(day) + (", so far" if day == today else ""),
            [count_text(value) for value in values[:USERS]] + [counted_text(values[USERS], "user")],
            f"{changelist_url}?created_at__year={day.year}&created_at__month={day.month}&created_at__day={day.day}",
        )
        columns.append((axis.day_x(day), [again, len(of_day) - again]))
        rows.append([day_text(day)] + [count_text(value) for value in values])

    plot = Plot(
        axis,
        label="Exports per day: exported again, and first exports",
        height=220,
        max_value=max((len(of_day) for of_day in by_day.values()), default=0) * 1.05,
        integer=True,
    )
    plot.add_columns(columns, [color for color, _ in PARTS])
    plot.hover_on(source, [
        {"field": AGAIN, "label": "exported again", "color": "series-1"},
        {"field": FIRST, "label": "exported the first time", "color": "other"},
        {"field": USERS, "label": "", "color": None},
    ], crosshair=False)

    range_text = f"{day_text(axis.days[0])} to {day_text(axis.days[-1])}, UTC"
    if axis.days[0] == recorded_from:
        range_text += f". Exports are recorded from {day_text(recorded_from)}."
    context.update({
        "range_text": range_text,
        "tiles": [
            Tile("Exports", count_text(len(in_window))),
            Tile("Exported again", count_text(sum(export["again"] for export in in_window)), "Made before, on an earlier day"),
            Tile("Users who exported", count_text(len({export["user_id"] for export in in_window}))),
            Tile(
                "Users who came back",
                count_text(len({export["user_id"] for export in in_window if export["again"]})),
                "Exported something again",
            ),
        ],
        "figures": [Figure(
            key="exports",
            title="Exports per day",
            subtitle="Lists and searches downloaded as files. Exported again means the same user had exported the"
                " same list or search on an earlier day: they came back for fresher numbers. Weekends are shaded.",
            plots=[plot],
            legend=[LegendItem(label, color, "rect") for color, label in PARTS],
            table_headers=["Day", "Exports", "Exported again", "First export", "Users"],
            table_rows=rows,
        )],
        "hover_sources": [source],
    })
    return context
