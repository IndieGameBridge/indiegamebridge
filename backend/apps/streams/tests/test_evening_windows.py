"""Tests for the parts of the day named after where it's evening then: how a stream's time
splits across them, which one holds most of it, and the profile's shares."""

from datetime import datetime, timezone as dt_timezone

from django.test import SimpleTestCase

from apps.streams.evening_windows import EVENING_WINDOW_CODES, main_window, seconds_by_window
from apps.streams.profile import StreamerProfileStreams

HOUR = 3600


def utc(*moment):
    return datetime(*moment, tzinfo=dt_timezone.utc)


class SecondsByWindowTests(SimpleTestCase):
    def test_the_pages_list_the_windows_west_to_east(self):
        self.assertEqual(EVENING_WINDOW_CODES, ("americas", "europe", "asia"))

    def test_a_stream_inside_one_window(self):
        self.assertEqual(
            seconds_by_window(utc(2026, 11, 3, 16), 4 * HOUR),
            {"americas": 0, "europe": 4 * HOUR, "asia": 0},
        )

    def test_a_stream_across_a_boundary_splits_there(self):
        # 14:00 to 17:00 UTC: an hour of Asia's evening, then two of Europe's.
        self.assertEqual(
            seconds_by_window(utc(2026, 11, 3, 14), 3 * HOUR),
            {"americas": 0, "europe": 2 * HOUR, "asia": HOUR},
        )

    def test_a_stream_across_midnight_stays_in_the_americas_window(self):
        # 23:30 to 03:30 UTC lies wholly in 23:00-07:00.
        self.assertEqual(
            seconds_by_window(utc(2026, 11, 3, 23, 30), 4 * HOUR),
            {"americas": 4 * HOUR, "europe": 0, "asia": 0},
        )

    def test_a_day_long_stream_fills_every_window(self):
        self.assertEqual(
            seconds_by_window(utc(2026, 11, 3, 7), 24 * HOUR),
            {"americas": 8 * HOUR, "europe": 8 * HOUR, "asia": 8 * HOUR},
        )

    def test_a_stream_with_no_length_has_no_time(self):
        self.assertEqual(seconds_by_window(utc(2026, 11, 3, 16), 0), {"americas": 0, "europe": 0, "asia": 0})


class MainWindowTests(SimpleTestCase):
    def test_the_window_with_the_most_time(self):
        self.assertEqual(main_window({"americas": 1, "europe": 5, "asia": 3}), "europe")

    def test_a_tie_goes_to_the_window_listed_first(self):
        self.assertEqual(main_window({"americas": 2, "europe": 2, "asia": 0}), "americas")
        self.assertEqual(main_window({"americas": 0, "europe": 2, "asia": 2}), "europe")

    def test_no_time_is_no_window(self):
        self.assertEqual(main_window({"americas": 0, "europe": 0, "asia": 0}), "")


class ProfileWindowsTests(SimpleTestCase):
    def test_the_share_of_the_recent_time_in_each_window(self):
        rows = [
            {"started_at": utc(2026, 11, 3, 16), "duration": 3 * HOUR},  # Europe & Africa
            {"started_at": utc(2026, 11, 4, 1), "duration": HOUR},  # Americas
        ]

        windows = StreamerProfileStreams._build_windows(rows)

        self.assertEqual(
            [(window["code"], window["hours"], window["share"]) for window in windows],
            [("americas", 1.0, 25), ("europe", 3.0, 75), ("asia", 0.0, 0)],
        )
        self.assertEqual(windows[0]["utc_hours"], "23:00–07:00 UTC")

    def test_no_streams_give_no_shares(self):
        self.assertEqual(
            [window["share"] for window in StreamerProfileStreams._build_windows([])],
            [0, 0, 0],
        )
