"""Tests for the admin's CSV exports: the dropdown's sizes and how cells are written."""

from datetime import UTC, datetime

from django.test import SimpleTestCase

from core.utils.admin_export import EXPORT_SIZES, _cell, days_between, export_size, last_line, seconds, utc_minute


class ExportSizeTests(SimpleTestCase):
    def test_offers_100_to_1000_rows_in_hundreds(self):
        self.assertEqual(EXPORT_SIZES, (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000))

    def test_takes_one_of_the_choices(self):
        self.assertEqual(export_size("300"), 300)

    def test_anything_else_is_the_smallest(self):
        for raw in (None, "", "abc", "150", "5000", "-100"):
            with self.subTest(raw=raw):
                self.assertEqual(export_size(raw), 100)


class CellTests(SimpleTestCase):
    def test_times_are_utc_to_the_minute(self):
        self.assertEqual(utc_minute(datetime(2026, 11, 10, 8, 12, 59, tzinfo=UTC)), "2026-11-10 08:12")
        self.assertEqual(utc_minute(None), "")

    def test_days_between_are_to_a_tenth(self):
        earlier = datetime(2026, 11, 1, tzinfo=UTC)

        self.assertEqual(days_between(earlier, datetime(2026, 11, 4, 12, tzinfo=UTC)), 3.5)
        self.assertEqual(days_between(None, earlier), "")

    def test_seconds_are_to_a_tenth(self):
        self.assertEqual(seconds(312.44), 312.4)
        self.assertEqual(seconds(None), "")

    def test_an_error_is_its_last_line(self):
        traceback = 'Traceback (most recent call last):\n  File "x.py", line 1\nValueError: bad month\n\n'

        self.assertEqual(last_line(traceback), "ValueError: bad month")
        self.assertEqual(last_line(""), "")

    def test_text_a_spreadsheet_would_run_stays_text(self):
        self.assertEqual(_cell("--month 2026-07"), "'--month 2026-07")
        self.assertEqual(_cell("rebuild_search_stats"), "rebuild_search_stats")
        self.assertEqual(_cell(5), 5)
