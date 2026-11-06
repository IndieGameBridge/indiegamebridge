"""Tests for the admin's Job runs > Busy time page."""

import json
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.fetch.models import FetchRun
from apps.jobs.busy_time import FREE, WINDOW_MINUTES, busy_time
from apps.jobs.models import JobRun

User = get_user_model()

# Thursday, half a minute past noon, UTC. The minute under way is the window's last, so
# the window runs from 09:01 to 12:01.
NOW = datetime(2026, 10, 29, 12, 0, 30, tzinfo=dt_timezone.utc)
START = datetime(2026, 10, 29, 9, 1, tzinfo=dt_timezone.utc)


def _at(minute, second=0):
    """A moment in the window, by its minute there."""
    return START + timedelta(minutes=minute, seconds=second)


def _run(job, started_at, duration=30, status=JobRun.Status.SUCCEEDED, **fields):
    return JobRun.objects.create(
        job=job,
        started_at=started_at,
        finished_at=None if duration is None else started_at + timedelta(seconds=duration),
        duration_seconds=duration,
        status=status,
        **fields,
    )


def _fetch_run(started_at, duration=180):
    return FetchRun.objects.create(
        started_at=started_at, finished_at=started_at + timedelta(seconds=duration), duration_seconds=duration,
        status=FetchRun.Status.SUCCEEDED,
    )


def _timeline(context):
    return context["figures"][0].plots[0]


def _minutes(context, label):
    """The minutes a row's tooltip has something to say for: a job's, or FREE's."""
    fields = json.loads(_timeline(context).fields_json)
    field = FREE if label == FREE else next(one["field"] for one in fields if one["label"] == label)
    return [index for index, row in enumerate(context["hover_sources"][0].rows) if row["values"][field]]


def _rows(context):
    return [row.label for row in _timeline(context).rows]


def _tiles(context):
    return {tile.label: tile for tile in context["tiles"]}


class BusyTimeTests(TestCase):
    def setUp(self):
        # Records from long ago, so every offset is on offer.
        _run("refresh_distribution", NOW - timedelta(days=60))

    def test_a_run_takes_every_minute_it_touches(self):
        _run("approve_streams", _at(10, 50), duration=20)

        self.assertEqual(_minutes(busy_time("", now=NOW), "approve_streams"), [10, 11])

    def test_a_run_of_a_second_still_takes_its_minute(self):
        _run("categorize_games", _at(34, 3), duration=1)

        self.assertEqual(_minutes(busy_time("", now=NOW), "categorize_games"), [34])

    def test_only_a_runs_minutes_inside_the_window_count(self):
        _run("rebuild_search_stats", _at(-3), duration=5 * 60)
        _run("rebuild_game_stats", _at(WINDOW_MINUTES - 2), duration=10 * 60)
        _run("rebuild_genre_stats", _at(WINDOW_MINUTES), duration=60)
        _run("approve_streams", _at(-3), duration=30)

        context = busy_time("", now=NOW)

        self.assertEqual(_minutes(context, "rebuild_search_stats"), [0, 1, 2])
        self.assertEqual(_minutes(context, "rebuild_game_stats"), [178, 179])
        self.assertEqual(_rows(context), ["Free", "rebuild_search_stats", "rebuild_game_stats"])

    def test_the_fetch_comes_first_and_jobs_with_no_runs_have_no_row(self):
        _run("update_cached_pages", _at(5))
        _run("approve_streams", _at(6))
        _fetch_run(_at(20))

        self.assertEqual(
            _rows(busy_time("", now=NOW)), ["Free", "fetch_twitch_streams", "approve_streams", "update_cached_pages"],
        )

    def test_the_free_row_holds_the_minutes_nothing_ran(self):
        _fetch_run(_at(0), duration=170)
        _run("approve_streams", _at(100), duration=10)

        context = busy_time("", now=NOW)
        free = _minutes(context, FREE)

        self.assertEqual(len(free), WINDOW_MINUTES - 4)
        self.assertEqual(free[:2], [3, 4])
        self.assertNotIn(100, free)
        tiles = _tiles(context)
        self.assertEqual((tiles["Free minutes"].value, tiles["Free minutes"].note), ("176", "of 180"))
        self.assertEqual(tiles["Longest free stretch"].value, "97 min")
        self.assertEqual(tiles["Longest free stretch"].note, "09:04 to 10:41 UTC")

    def test_a_window_with_no_free_minute(self):
        _run("archive_streams", _at(-10), duration=4 * 3600)

        tiles = _tiles(busy_time("", now=NOW))

        self.assertEqual(tiles["Free minutes"].value, "0")
        self.assertEqual((tiles["Longest free stretch"].value, tiles["Longest free stretch"].note), ("None", ""))

    def test_a_window_with_nothing_in_it_is_all_free(self):
        context = busy_time("", now=NOW)

        self.assertEqual(_rows(context), ["Free"])
        self.assertEqual(_tiles(context)["Free minutes"].value, "180")

    def test_the_table_lists_the_free_stretches_worth_planning_around(self):
        # Free for 4 minutes, then 3, then exactly 5, then the rest but for the last 10.
        for minute in (4, 8, 14):
            _run("approve_streams", _at(minute), duration=10)
        _run("approve_streams", _at(170), duration=10 * 60)

        figure = busy_time("", now=NOW)["figures"][0]

        self.assertEqual(figure.table_title, "Free stretches of 5 minutes or more")
        self.assertEqual(
            [[cell.text for cell in row] for row in figure.table_rows],
            [["09:10", "09:15", "5"], ["09:16", "11:51", "155"]],
        )

    def test_counts_the_minutes_with_two_or_more_jobs(self):
        _fetch_run(_at(0), duration=170)
        _run("approve_streams", _at(1), duration=10)
        _run("enrich_igdb_games", _at(2), duration=10)

        self.assertEqual(_tiles(busy_time("", now=NOW))["Minutes with 2+ jobs"].value, "2")

    def test_a_minute_tooltip_says_what_ran_and_opens_it(self):
        run = _run("rebuild_search_stats", _at(10), duration=309)
        _run("approve_streams", _at(11), duration=4)

        context = busy_time("", now=NOW)
        row = context["hover_sources"][0].rows[11]

        self.assertEqual(row["title"], "Thu 29 Oct, 09:12 UTC")
        self.assertIn("5m 09s", row["values"])
        self.assertIn("4s", row["values"])
        # The longer run is the one a click opens.
        self.assertEqual(row["url"], reverse("admin:jobs_jobrun_change", args=[run.pk]))
        self.assertIsNone(context["hover_sources"][0].rows[20]["url"])

    def test_a_run_under_way_takes_the_minutes_up_to_now(self):
        _run("rebuild_game_stats", NOW - timedelta(minutes=3), duration=None, status=JobRun.Status.RUNNING)

        context = busy_time("", now=NOW)

        self.assertEqual(_minutes(context, "rebuild_game_stats"), [176, 177, 178, 179])
        self.assertIn("Running", context["hover_sources"][0].rows[179]["values"])

    def test_a_run_that_never_finished_takes_only_its_first_minute(self):
        _run("rebuild_game_stats", _at(30), duration=None, status=JobRun.Status.RUNNING)
        FetchRun.objects.create(started_at=_at(10), status=FetchRun.Status.RUNNING)

        # Three hours on, the same window, and both are long given up on.
        context = busy_time("3", now=NOW + timedelta(hours=3))

        self.assertEqual(_minutes(context, "rebuild_game_stats"), [30])
        self.assertEqual(_minutes(context, "fetch_twitch_streams"), [10])
        self.assertIn("Never finished", context["hover_sources"][0].rows[30]["values"])
        self.assertEqual([item.label for item in context["figures"][0].legend], ["Failed or never finished"])

    def test_a_failed_run_stands_out(self):
        _run("rebuild_genre_stats", _at(10), duration=90, status=JobRun.Status.FAILED)
        _run("approve_streams", _at(30))

        context = busy_time("", now=NOW)

        colors = {bar.x: bar.color for bar in _timeline(context).bars}
        self.assertEqual(colors[40], "critical")
        self.assertEqual(colors[120], "series-1")
        self.assertEqual([item.label for item in context["figures"][0].legend], ["Failed or never finished"])
        self.assertIn("Failed after 1m 30s", context["hover_sources"][0].rows[10]["values"])

    def test_no_legend_without_a_failed_run(self):
        _run("approve_streams", _at(30))

        self.assertEqual(busy_time("", now=NOW)["figures"][0].legend, [])

    def test_the_offset_moves_the_window_back(self):
        _run("approve_streams", _at(10))
        _run("approve_streams", _at(-170))

        context = busy_time("3", now=NOW)

        self.assertEqual(context["range_text"], "Thu 29 Oct, 06:01 to 09:01 UTC")
        self.assertEqual(_minutes(context, "approve_streams"), [10])

    def test_offsets_step_back_a_window_at_a_time_for_a_week(self):
        options = busy_time("6", now=NOW)["select"]["options"]

        self.assertEqual([option["label"] for option in options[:3]], ["Latest", "3 hours ago", "6 hours ago"])
        self.assertEqual(options[9]["label"], "1 day 3 hours ago")
        self.assertEqual(options[8]["label"], "1 day ago")
        self.assertEqual((options[-1]["value"], options[-1]["label"]), (168, "7 days ago"))
        self.assertEqual([option["value"] for option in options if option["selected"]], [6])

    def test_offsets_stop_where_the_records_start(self):
        JobRun.objects.all().delete()
        _run("approve_streams", NOW - timedelta(hours=10))

        options = busy_time("", now=NOW)["select"]["options"]

        self.assertEqual([option["value"] for option in options], [0, 3, 6])

    def test_a_bad_offset_shows_the_latest(self):
        for raw in ("", None, "abc", "4", "-3", "9999"):
            with self.subTest(raw=raw):
                self.assertEqual(busy_time(raw, now=NOW)["range_text"], "Thu 29 Oct, 09:01 to 12:01 UTC")

    def test_a_window_across_midnight_names_both_days(self):
        context = busy_time("", now=datetime(2026, 10, 30, 1, 0, tzinfo=dt_timezone.utc))

        self.assertEqual(context["range_text"], "Thu 29 Oct, 22:01 to Fri 30 Oct, 01:01 UTC")
        self.assertIn("Fri 00:00", [label.text for label in _timeline(context).x_labels])

    def test_time_labels_fall_on_the_clocks_quarters(self):
        texts = [label.text for label in _timeline(busy_time("", now=NOW)).x_labels]

        self.assertEqual(texts[:2], ["09:15", "09:30"])
        self.assertEqual(texts[-1], "11:45")

    def test_nothing_recorded_yet(self):
        JobRun.objects.all().delete()

        context = busy_time("", now=NOW)

        self.assertNotIn("figures", context)
        self.assertEqual(context["empty_text"], "No job runs are recorded yet.")


class BusyTimePageTests(TestCase):
    def setUp(self):
        self.url = reverse("admin:jobs_jobrun_busy_time")

    def test_shows_the_timeline_and_its_dropdown(self):
        _run("approve_streams", datetime.now(dt_timezone.utc) - timedelta(hours=40))
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

        response = self.client.get(self.url, {"offset": "3"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Time offset")
        self.assertContains(response, 'value="3" selected')
        self.assertContains(response, 'class="viz-timeline"')
        self.assertNotContains(response, 'name="days"')
        self.assertContains(response, reverse("admin:jobs_jobrun_graphs"))

    def test_the_list_and_the_graphs_link_to_it(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

        for url in (reverse("admin:jobs_jobrun_changelist"), reverse("admin:jobs_jobrun_graphs")):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), f'href="{self.url}"')

    def test_needs_the_view_permission(self):
        self.client.force_login(User.objects.create_user(username="staff", is_staff=True))

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_needs_a_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
