"""Tests for the export files: what each format writes from the same rows."""

import csv
import dataclasses
import io
import json
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree

from django.test import SimpleTestCase

from apps.exports.files import About, write_csv, write_json, write_xlsx
from apps.exports.models import Export
from apps.exports.rows import LIST_COLUMNS

SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

ABOUT = About(
    source=Export.Source.LIST,
    url="https://indiegamebridge.test/lists/7",
    exported_at=datetime(2026, 10, 28, 14, 3, 59, tzinfo=UTC),
    title="to contact",
    search=[{"label": "Language", "value": "English"}, {"label": "Max Viewers", "value": "5–200"}],
)


def _row(**overrides) -> dict:
    row = {
        "twitch_login": "smallstreamer",
        "display_name": "SmallStreamer",
        "twitch_url": "https://www.twitch.tv/smallstreamer",
        "language": "English",
        "max_viewers": 40,
        "avg_viewers": 12,
        "hours_streamed": 30,
        "streams": 9,
        "genres": ["Indie", "Platform"],
        "twitch_user_id": "123456789",
        "note": "replied, wants a key",
        "added_at": datetime(2026, 10, 20, 9, 30, tzinfo=UTC),
    }
    row.update(overrides)
    return row


def _xlsx_cells(content: bytes, sheet: int = 1) -> dict:
    """A sheet's cells by reference ("A1"): text, a number, or ("formula", ...)."""
    xlsx = zipfile.ZipFile(io.BytesIO(content))
    shared = [
        "".join(node.itertext())
        for node in ElementTree.fromstring(xlsx.read("xl/sharedStrings.xml")).findall("x:si", SHEET_NS)
    ]
    cells = {}
    for cell in ElementTree.fromstring(xlsx.read(f"xl/worksheets/sheet{sheet}.xml")).iter(f"{{{SHEET_NS['x']}}}c"):
        formula = cell.find("x:f", SHEET_NS)
        value = cell.find("x:v", SHEET_NS)
        if formula is not None:
            cells[cell.get("r")] = ("formula", formula.text)
        elif cell.get("t") == "s":
            cells[cell.get("r")] = shared[int(value.text)]
        elif value is not None:
            cells[cell.get("r")] = float(value.text)
    return cells


class CsvTests(SimpleTestCase):
    def _read(self, rows) -> list[list[str]]:
        return list(csv.reader(io.StringIO(write_csv(rows, LIST_COLUMNS, ABOUT).decode("utf-8-sig"))))

    def test_starts_with_the_byte_order_mark_excel_needs_for_utf8(self):
        self.assertTrue(write_csv([_row()], LIST_COLUMNS, ABOUT).startswith(b"\xef\xbb\xbf"))

    def test_writes_the_header_then_a_row_per_streamer(self):
        header, row = self._read([_row()])

        self.assertEqual(header, [header for _, header in LIST_COLUMNS])
        self.assertEqual(row, [
            "smallstreamer", "SmallStreamer", "https://www.twitch.tv/smallstreamer", "English",
            "40", "12", "30", "9", "Indie, Platform", "123456789",
            "replied, wants a key", "2026-10-20 09:30",
        ])

    def test_text_that_would_run_as_a_formula_stays_text(self):
        for note in ('=HYPERLINK("https://example.com")', "+1", "-1", "@SUM(A1)"):
            with self.subTest(note=note):
                _, row = self._read([_row(note=note)])
                self.assertEqual(row[-2], f"'{note}")

    def test_a_streamer_without_stats_has_empty_cells(self):
        no_stats = dict.fromkeys(("language", "max_viewers", "avg_viewers", "hours_streamed", "streams", "genres"))

        _, row = self._read([_row(**no_stats)])

        self.assertEqual(row[3:9], [""] * 6)


class XlsxTests(SimpleTestCase):
    def test_puts_the_streamers_first_and_the_export_details_second(self):
        workbook = zipfile.ZipFile(io.BytesIO(write_xlsx([_row()], LIST_COLUMNS, ABOUT))).read("xl/workbook.xml")

        sheets = [sheet.get("name") for sheet in ElementTree.fromstring(workbook).iter(f"{{{SHEET_NS['x']}}}sheet")]
        self.assertEqual(sheets, ["Streamers", "About"])

    def test_writes_numbers_as_numbers_and_dates_as_dates(self):
        cells = _xlsx_cells(write_xlsx([_row()], LIST_COLUMNS, ABOUT))

        self.assertEqual((cells["A1"], cells["A2"]), ("Twitch login", "smallstreamer"))
        self.assertEqual((cells["E2"], cells["H2"]), (40, 9))
        self.assertEqual(cells["I2"], "Indie, Platform")
        # The Twitch user id is text, as Twitch gives it.
        self.assertEqual(cells["J2"], "123456789")
        # Excel counts days from 1899-12-30; the time of day is the fraction.
        days = (datetime(2026, 10, 20, 9, 30) - datetime(1899, 12, 30)).total_seconds() / 86400
        self.assertAlmostEqual(cells["L2"], days)

    def test_text_that_looks_like_a_formula_is_written_as_text(self):
        cells = _xlsx_cells(write_xlsx([_row(note="=1+1")], LIST_COLUMNS, ABOUT))

        self.assertEqual(cells["K2"], "=1+1")

    def test_the_channel_is_a_link(self):
        sheet = zipfile.ZipFile(io.BytesIO(write_xlsx([_row()], LIST_COLUMNS, ABOUT))).read("xl/worksheets/sheet1.xml")

        links = [link.get("ref") for link in ElementTree.fromstring(sheet).iter(f"{{{SHEET_NS['x']}}}hyperlink")]
        self.assertEqual(links, ["C2"])

    def test_says_when_and_where_it_came_from(self):
        cells = _xlsx_cells(write_xlsx([_row()], LIST_COLUMNS, ABOUT), sheet=2)

        about = {cells[f"A{row}"]: cells[f"B{row}"] for row in range(1, 6)}
        self.assertEqual(about["Exported"], "2026-10-28 14:03 UTC")
        self.assertEqual(about["List"], "to contact")
        self.assertEqual(about["Saved from"], "Language: English · Max Viewers: 5–200")
        self.assertEqual(about["Open on IndieGameBridge"], "https://indiegamebridge.test/lists/7")

    def test_counts_the_streamers_who_opted_out(self):
        about = dataclasses.replace(ABOUT, removed_streamers=2)

        cells = _xlsx_cells(write_xlsx([_row()], LIST_COLUMNS, about), sheet=2)

        self.assertEqual(cells["A6"], "Opted out")
        self.assertTrue(cells["B6"].startswith("2 of these streamers opted out"))

    def test_an_empty_list_is_still_a_file_with_its_header(self):
        cells = _xlsx_cells(write_xlsx([], LIST_COLUMNS, ABOUT))

        self.assertEqual(cells["A1"], "Twitch login")
        self.assertNotIn("A2", cells)


class JsonTests(SimpleTestCase):
    def _read(self, rows) -> dict:
        return json.loads(write_json(rows, LIST_COLUMNS, ABOUT))

    def test_says_when_and_where_it_came_from(self):
        data = self._read([_row()])

        self.assertEqual(data["exported_at"], "2026-10-28T14:03:59+00:00")
        self.assertEqual((data["source"], data["title"]), ("list", "to contact"))
        self.assertEqual(data["url"], "https://indiegamebridge.test/lists/7")
        self.assertEqual(data["search"], ABOUT.search)
        self.assertEqual(data["stats_window_days"], 28)

    def test_writes_each_streamer_with_its_values_typed(self):
        (streamer,) = self._read([_row()])["streamers"]

        self.assertEqual(list(streamer), [key for key, _ in LIST_COLUMNS])
        self.assertEqual(streamer["max_viewers"], 40)
        self.assertEqual(streamer["genres"], ["Indie", "Platform"])
        self.assertEqual(streamer["twitch_user_id"], "123456789")
        self.assertEqual(streamer["added_at"], "2026-10-20T09:30:00+00:00")

    def test_keeps_names_as_spelled(self):
        content = write_json([_row(display_name="Zoé")], LIST_COLUMNS, ABOUT)

        self.assertIn("Zoé".encode(), content)
