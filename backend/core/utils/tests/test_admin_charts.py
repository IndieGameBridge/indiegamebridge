"""Tests for the admin graph pages' chart pieces: ticks, texts, the time axis and the paths."""

from datetime import date, datetime, timezone as dt_timezone

from django.test import SimpleTestCase

from core.utils.admin_charts import (
    DEFAULT_WINDOW,
    Plot,
    TimeAxis,
    compact_text,
    counted_text,
    duration_text,
    line_path,
    nice_ticks,
    window_days,
)

# Fri 23 Oct to Mon 26 Oct 2026: four days, two of them a weekend.
FIRST_DAY, LAST_DAY = date(2026, 10, 23), date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 6, 0, tzinfo=dt_timezone.utc)


class NiceTicksTests(SimpleTestCase):
    def test_round_steps_past_the_top(self):
        self.assertEqual(nice_ticks(10.5), ([0, 5, 10, 15], 15))
        self.assertEqual(nice_ticks(840), ([0, 250, 500, 750, 1000], 1000))

    def test_integer_scales_step_by_whole_numbers(self):
        self.assertEqual(nice_ticks(3, integer=True), ([0, 1, 2, 3], 3))
        self.assertEqual(nice_ticks(0, integer=True), ([0, 1], 1))


class TextTests(SimpleTestCase):
    def test_durations(self):
        self.assertEqual(duration_text(45), "45s")
        self.assertEqual(duration_text(369), "6m 09s")
        self.assertEqual(duration_text(3720), "1h 02m")

    def test_counts_with_their_noun(self):
        self.assertEqual(counted_text(1, "run"), "1 run")
        self.assertEqual(counted_text(1072, "run"), "1,072 runs")

    def test_compact_numbers(self):
        self.assertEqual(
            [compact_text(value) for value in (0, 500, 2500, 20000, 1250000)],
            ["0", "500", "2.5K", "20K", "1.25M"],
        )

    def test_window_days_falls_back_to_the_default(self):
        self.assertEqual(window_days("7"), 7)
        for raw in (None, "", "8", "abc"):
            self.assertEqual(window_days(raw), DEFAULT_WINDOW)


class TimeAxisTests(SimpleTestCase):
    def test_days_are_day_width_wide(self):
        axis = TimeAxis(FIRST_DAY, LAST_DAY, 720, NOW)
        self.assertEqual(axis.width, 2880)
        self.assertEqual(axis.x(datetime(2026, 10, 24, 6, tzinfo=dt_timezone.utc)), 900)
        self.assertEqual(axis.day_x(FIRST_DAY), 360)
        self.assertEqual(axis.now, 2340)
        self.assertEqual(axis.percent(axis.now), 81.25)

    def test_shades_the_weekend_and_marks_where_days_meet(self):
        axis = TimeAxis(FIRST_DAY, LAST_DAY, 720, NOW)
        self.assertEqual([band.x for band in axis.weekends()], [720, 1440])
        self.assertEqual(axis.midnights(), [720, 1440, 2160])

    def test_wide_days_get_their_hours(self):
        labels = TimeAxis(FIRST_DAY, FIRST_DAY, 720, NOW).labels()
        self.assertEqual([(label.text, label.kind) for label in labels], [
            ("Fri 23", "day"), ("06:00", "hour"), ("12:00", "hour"), ("18:00", "hour"),
        ])
        self.assertEqual(labels[2].left, 50)

    def test_narrow_days_get_a_name_under_their_middle(self):
        labels = TimeAxis(FIRST_DAY, LAST_DAY, 72, NOW).labels()
        self.assertEqual([label.text for label in labels], ["Fri 23", "Sat 24", "Sun 25", "Mon 26"])
        self.assertEqual(labels[0].left, 12.5)

    def test_days_of_one_column_keep_close_together(self):
        axis = TimeAxis(FIRST_DAY, LAST_DAY, 32, NOW, stretch=False)
        # Names every other day, so they don't run into each other, and no lines between days.
        self.assertEqual([label.text for label in axis.labels()], ["Fri 23", "Sun 25"])
        self.assertEqual(axis.midnights(), [])
        self.assertFalse(Plot(axis, label="", height=150, max_value=1).stretch)


class PathTests(SimpleTestCase):
    def test_a_gap_breaks_the_line(self):
        self.assertEqual(line_path([(1, 2), (3, 4), None, (5, 6), (7, 8)]), "M1,2L3,4M5,6L7,8")

    def test_a_lone_point_still_shows(self):
        self.assertEqual(line_path([(1, 2), None, (5, 6)]), "M1,2L1,2M5,6L5,6")

    def test_stacked_columns_leave_a_gap_and_round_the_top_part_only(self):
        plot = Plot(TimeAxis(FIRST_DAY, FIRST_DAY, 72, NOW), label="", height=128, max_value=10, integer=True)
        plot.add_columns([(36, [4, 6])], ["series-1", "other"])

        column = plot.columns[0]
        lower, upper = column.parts
        # On a 0-10 scale the plot is 88 high, its base at 100: the lower part is 4
        # (35.2) tall, square; the upper one starts 2 above it, and is rounded.
        self.assertEqual(column.left, 50)
        self.assertEqual((lower.top, lower.height, lower.rounded), (64.8, 35.2, False))
        self.assertEqual((upper.top, upper.height, upper.rounded), (12, 50.8, True))
