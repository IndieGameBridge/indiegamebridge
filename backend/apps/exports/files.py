"""The export files - Excel, CSV and JSON - each written from the same rows."""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import xlsxwriter

from apps.exports.models import Export
from apps.streams.management.commands.rebuild_search_stats import WINDOW_DAYS

# A cell starting with one of these is a formula to Excel and the other
# spreadsheet apps. Notes are free text, so a CSV cell like that gets a leading
# apostrophe, which they show as text; the Excel file writes every text cell
# as text anyway.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Excel column widths in characters, for the columns the default is too narrow for.
XLSX_COLUMN_WIDTHS = {
    "twitch_login": 20,
    "display_name": 20,
    "twitch_url": 36,
    "genres": 40,
    "twitch_user_id": 14,
    "note": 50,
    "added_at": 18,
}


@dataclass
class About:
    """What a file says about itself besides its rows: where it came from, and when."""

    source: str
    # The list or search on the site, for fresh numbers once the file's are old.
    url: str
    exported_at: datetime
    # The list's title; empty for a search.
    title: str = ""
    # The search's filters as StreamerSearch.describe() gives them: the one
    # exported, or the one a list was saved from.
    search: list[dict] = field(default_factory=list)
    # List entries whose streamer has since opted out.
    removed_streamers: int = 0

    def lines(self) -> list[tuple[str, str, bool]]:
        """Label, text, and whether the text is a link: the Excel file's About sheet."""
        lines = [("Exported", f"{self.exported_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC", False)]
        if self.title:
            lines.append(("List", self.title, False))
        if self.search:
            label = "Saved from" if self.source == Export.Source.LIST else "Search"
            lines.append((label, " · ".join(f"{one['label']}: {one['value']}" for one in self.search), False))
        lines.append(("Open on IndieGameBridge", self.url, True))
        lines.append(("Stats", f"From each streamer's streams in the {WINDOW_DAYS} days before the export.", False))
        if self.removed_streamers:
            lines.append((
                "Opted out",
                f"{self.removed_streamers} of these streamers opted out, so their rows keep only your note.",
                False,
            ))
        return lines


def write_xlsx(rows: list[dict], columns, about: About) -> bytes:
    buffer = io.BytesIO()
    # in_memory builds the file in RAM rather than in temp files. Excel has no
    # time zones, so dates go in as UTC with the zone dropped.
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True, "remove_timezone": True})
    bold = workbook.add_format({"bold": True})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})

    sheet = workbook.add_worksheet("Streamers")
    for col, (key, header) in enumerate(columns):
        sheet.write_string(0, col, header, bold)
        sheet.set_column(col, col, XLSX_COLUMN_WIDTHS.get(key, 12))
    for row_index, row in enumerate(rows, start=1):
        for col, (key, _) in enumerate(columns):
            value = row[key]
            if value is None:
                continue
            if key == "twitch_url":
                sheet.write_url(row_index, col, value, string=value)
            elif isinstance(value, datetime):
                sheet.write_datetime(row_index, col, value.astimezone(UTC), date_format)
            elif isinstance(value, int):
                sheet.write_number(row_index, col, value)
            else:
                sheet.write_string(row_index, col, _text(value))
    # The header stays in view while scrolling, with a filter on every column.
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, len(rows), len(columns) - 1)

    about_sheet = workbook.add_worksheet("About")
    about_sheet.set_column(0, 0, 24)
    about_sheet.set_column(1, 1, 90)
    for row_index, (label, text, is_link) in enumerate(about.lines()):
        about_sheet.write_string(row_index, 0, label, bold)
        if is_link:
            about_sheet.write_url(row_index, 1, text, string=text)
        else:
            about_sheet.write_string(row_index, 1, text)

    workbook.close()
    return buffer.getvalue()


def write_csv(rows: list[dict], columns, about: About) -> bytes:
    # Rows only: a line about the export would break the imports a CSV is for.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header for _, header in columns)
    for row in rows:
        writer.writerow(_csv_cell(row[key]) for key, _ in columns)
    # Excel reads a CSV as UTF-8 only when it starts with a byte order mark.
    return buffer.getvalue().encode("utf-8-sig")


def write_json(rows: list[dict], columns, about: About) -> bytes:
    payload = {
        "exported_from": "IndieGameBridge",
        "exported_at": about.exported_at.isoformat(timespec="seconds"),
        "source": about.source,
        "title": about.title or None,
        "search": about.search,
        "url": about.url,
        "stats_window_days": WINDOW_DAYS,
        "streamers": [{key: _json_value(row[key]) for key, _ in columns} for row in rows],
    }
    # Indented for reading in an editor; names stay as spelled, not \u-escaped.
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# Each format's content type and writer; the format is also the file extension.
FILE_TYPES = {
    Export.FileFormat.XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        write_xlsx,
    ),
    Export.FileFormat.CSV: ("text/csv; charset=utf-8", write_csv),
    Export.FileFormat.JSON: ("application/json", write_json),
}


def _text(value) -> str:
    """A cell's text: genres joined, dates in UTC to the minute."""
    if isinstance(value, list):
        return ", ".join(value)
    if isinstance(value, datetime):
        return f"{value.astimezone(UTC):%Y-%m-%d %H:%M}"
    return str(value)


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, int):
        return value
    text = _text(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value
