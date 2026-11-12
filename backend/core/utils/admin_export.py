"""Download a ModelAdmin's newest rows as a CSV file, from a dropdown on its changelist.

The files are for studying the site's use over time somewhere else: in a spreadsheet, or
handed to an LLM. So they hold what that needs and no more: a user is their number, with
no name, IP address or place finer than a country. CSV rather than JSON, since it names
each column once, which makes a file about half the size for the same rows.
"""

import csv
import io
from datetime import UTC

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import content_disposition_header

# How many of the newest rows a file can hold: the dropdown's choices.
EXPORT_SIZES = tuple(range(100, 1001, 100))

# A spreadsheet runs a cell starting with one of these as a formula, so such text gets
# a leading apostrophe, as in the site's own CSV exports.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# An error's last line, the exception and its message, is cut to this many characters.
ERROR_CHARS = 200


def export_size(raw) -> int:
    """The size asked for, or the smallest when it isn't one of the choices."""
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return EXPORT_SIZES[0]
    return size if size in EXPORT_SIZES else EXPORT_SIZES[0]


def utc_minute(value) -> str:
    """A datetime as "2026-11-10 08:12" in UTC; empty for none."""
    return "" if value is None else f"{value.astimezone(UTC):%Y-%m-%d %H:%M}"


def days_between(earlier, later):
    """The days from one datetime to a later one, to a tenth; empty when there's no earlier."""
    return "" if earlier is None else round((later - earlier).total_seconds() / 86400, 1)


def minutes_between(earlier, later):
    """The whole minutes from one datetime to a later one; empty when there's no earlier."""
    return "" if earlier is None else int((later - earlier).total_seconds() // 60)


def seconds(value):
    """Seconds to a tenth; empty until set."""
    return "" if value is None else round(value, 1)


def last_line(text: str) -> str:
    """A traceback's last line: the exception and its message, which is what says what went wrong."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1][:ERROR_CHARS] if lines else ""


class CsvExportAdminMixin:
    """An export/ page under a ModelAdmin's changelist, which downloads its newest rows.

    export_rows(size) gives the header and up to `size` rows, newest first; export_name
    names the file. The changelist's template includes admin/export_form.html, which shows
    the dropdown once changelist_view has put the sizes in its context.
    """

    export_name = "rows"

    def export_rows(self, size: int) -> tuple[list[str], list[list]]:
        raise NotImplementedError

    def get_urls(self):
        name = f"{self.opts.app_label}_{self.opts.model_name}_export"
        # Ahead of the ModelAdmin's own, whose <object_id>/ would take export/ for an id.
        return [path("export/", self.admin_site.admin_view(self.export_view), name=name), *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "export_sizes": EXPORT_SIZES})

    def export_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        size = export_size(request.GET.get("rows"))
        header, rows = self.export_rows(size)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        for row in rows:
            writer.writerow(_cell(value) for value in row)
        response = HttpResponse(buffer.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
        filename = f"indiegamebridge-{self.export_name}-last-{size}-{timezone.now():%Y-%m-%d}.csv"
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
        # Usage records: no shared cache may keep a copy.
        add_never_cache_headers(response)
        return response


def _cell(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value
