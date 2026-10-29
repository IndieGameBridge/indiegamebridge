"""Tests for the admin's Fetch runs > Graphs page."""

from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.fetch.graphs import busiest_minute, fetch_graphs
from apps.fetch.models import FetchRun, FetchRunLanguage

User = get_user_model()

# Thursday noon, UTC.
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=dt_timezone.utc)


def _language(*rounds):
    """A language's rounds, each as (requests, helix seconds, write seconds)."""
    return SimpleNamespace(rounds_detail=[
        {"requests": requests, "helix_seconds": helix, "write_seconds": write} for requests, helix, write in rounds
    ])


class BusiestMinuteTests(TestCase):
    def test_adds_up_the_languages_polling_side_by_side(self):
        en = _language((100, 10, 70), (100, 10, 70))
        de = _language((50, 5, 20))
        # en's first round and de's round both fall in the first minute; en's second starts at 80 s.
        self.assertAlmostEqual(busiest_minute([en, de]), 150)

    def test_short_rounds_are_spaced_out_to_the_minimum(self):
        # Rounds of 7 s still take 20 s each, so four of them span more than a minute.
        es = _language(*[(50, 2, 5)] * 4)
        self.assertAlmostEqual(busiest_minute([es]), 150)

    def test_a_run_with_no_rounds(self):
        self.assertEqual(busiest_minute([_language()]), 0)


class FetchGraphsTests(TestCase):
    def _run(self, started_at, duration=300, status=FetchRun.Status.SUCCEEDED, **fields):
        run = FetchRun.objects.create(
            started_at=started_at,
            finished_at=None if duration is None else started_at + timedelta(seconds=duration),
            duration_seconds=duration,
            status=status,
            finalize_seconds=None if duration is None else 5,
            streams_collected=1000,
            **fields,
        )
        FetchRunLanguage.objects.create(
            run=run,
            language="en",
            duration_seconds=None if duration is None else duration - 10,
            rounds=1,
            requests=100,
            helix_seconds=20,
            write_seconds=200,
            streams_created=40,
            profiles_created=4,
            rounds_detail=[{"requests": 100, "fetched": 900, "written": 900, "helix_seconds": 20, "write_seconds": 200}],
            error="NotUpdated: Save with update_fields did not affect any rows." if status == FetchRun.Status.FAILED else "",
        )
        return run

    def _figure(self, context, key):
        return next(figure for figure in context["figures"] if figure.key == key)

    def test_nothing_recorded_yet(self):
        context = fetch_graphs(14, now=NOW)
        self.assertNotIn("figures", context)
        self.assertEqual(context["empty_text"], "No fetch runs are recorded yet.")

    def test_tiles_count_runs_failures_and_the_missing(self):
        start = NOW - timedelta(hours=3)
        for index in range(9):
            # The 01:20 run is missing.
            if index != 4:
                self._run(start + index * timedelta(minutes=20), status=FetchRun.Status.FAILED if index == 2 else FetchRun.Status.SUCCEEDED)
        # Killed: still RUNNING two hours on.
        self._run(start - timedelta(minutes=20), duration=None, status=FetchRun.Status.RUNNING)

        tiles = {tile.label: tile for tile in fetch_graphs(14, now=NOW)["tiles"]}

        self.assertEqual(tiles["Runs"].value, "9")
        self.assertEqual(tiles["Runs"].note, "1 missing")
        self.assertEqual(tiles["Failed"].value, "2")
        self.assertEqual(tiles["Failed"].note, "1 never finished")

    def test_a_run_still_going_is_left_out(self):
        self._run(NOW - timedelta(minutes=40))
        self._run(NOW - timedelta(minutes=5), duration=None, status=FetchRun.Status.RUNNING)

        context = fetch_graphs(14, now=NOW)

        self.assertEqual(len(context["hover_sources"][0].rows), 1)
        self.assertEqual({tile.label: tile for tile in context["tiles"]}["Latest run"].note, "Running now")

    def test_lines_break_where_runs_are_missing(self):
        self._run(NOW - timedelta(hours=4))
        self._run(NOW - timedelta(hours=3, minutes=40))
        self._run(NOW - timedelta(hours=1))

        plot = self._figure(fetch_graphs(14, now=NOW), "run-time").plots[0]

        self.assertEqual(plot.lines[0].path.count("M"), 2)

    def test_marks_failed_runs_and_says_why(self):
        self._run(NOW - timedelta(hours=1), status=FetchRun.Status.FAILED)

        context = fetch_graphs(14, now=NOW)

        self.assertEqual([marker.kind for marker in self._figure(context, "run-time").plots[0].markers], ["critical"])
        status = context["hover_sources"][0].rows[0]["values"][1]
        self.assertIn("en: NotUpdated", status)

    def test_the_time_split_adds_up_to_the_run_time(self):
        self._run(NOW - timedelta(hours=1), duration=300)

        context = fetch_graphs(14, now=NOW)

        # en wrote for 200 s and waited on Helix 20 s, finalizing took 5 s: 75 s are left over.
        self.assertEqual(context["hover_sources"][0].rows[0]["values"][2:6], ["3m 20s", "20s", "5s", "1m 15s"])

    def test_days_total_new_streams_and_streamers(self):
        self._run(NOW - timedelta(hours=1))
        self._run(NOW - timedelta(hours=2))

        days = fetch_graphs(14, now=NOW)["hover_sources"][1]

        self.assertEqual(days.rows[-1]["values"], ["80", "8", "2 runs"])
        self.assertEqual(days.rows[-1]["title"], "Thu 29 Oct, so far")

    def _with_german(self, run, **fields):
        FetchRunLanguage.objects.create(**{
            "run": run, "language": "de", "duration_seconds": 120, "rounds": 1, "requests": 50,
            "helix_seconds": 5, "write_seconds": 60, "streams_written": 300, "streams_created": 10,
            "profiles_created": 1,
            "rounds_detail": [{"requests": 50, "fetched": 300, "written": 300, "helix_seconds": 5, "write_seconds": 60}],
            **fields,
        })

    def test_a_language_shows_its_own_polling(self):
        self._with_german(self._run(NOW - timedelta(hours=1), duration=300))

        context = fetch_graphs(14, language="de", now=NOW)

        values = context["hover_sources"][0].rows[0]["values"]
        # de polled for 120 s: 60 writing, 5 on Helix and 55 between, with no finalizing of its own.
        self.assertEqual(values[0], "2m 00s")
        self.assertEqual(values[2:6], ["1m 00s", "5s", None, "55s"])
        self.assertEqual(values[8], "300")
        self.assertEqual(context["hover_sources"][1].rows[-1]["values"][:2], ["10", "1"])
        self.assertEqual({tile.label: tile.value for tile in context["tiles"]}["Longest de polling"], "2m 00s")
        self.assertEqual(self._figure(context, "time-split").legend[2].label, "Other")

    def test_a_failure_marks_only_its_own_language(self):
        self._with_german(self._run(NOW - timedelta(hours=1), status=FetchRun.Status.FAILED))

        def markers(language):
            return self._figure(fetch_graphs(14, language=language, now=NOW), "run-time").plots[0].markers

        self.assertEqual(len(markers("en")), 1)
        self.assertEqual(markers("de"), [])

    def test_offers_the_languages_polled_most_streams_first(self):
        self._with_german(self._run(NOW - timedelta(hours=1)), streams_written=5000)

        select = fetch_graphs(14, language="xx", now=NOW)["select"]

        self.assertEqual([option["value"] for option in select["options"]], ["", "de", "en"])
        # An unknown language shows all of them.
        self.assertTrue(select["options"][0]["selected"])


class FetchGraphsPageTests(TestCase):
    def setUp(self):
        started_at = timezone.now() - timedelta(minutes=30)
        FetchRun.objects.create(
            started_at=started_at, finished_at=started_at + timedelta(minutes=5), duration_seconds=300,
            status=FetchRun.Status.SUCCEEDED, finalize_seconds=5,
        )
        self.url = reverse("admin:fetch_fetchrun_graphs")

    def test_renders_for_an_admin(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

        response = self.client.get(self.url, {"days": "7"})

        self.assertEqual(response.status_code, 200)
        # Run time, the time split and Helix, then five small plots of what was collected.
        self.assertContains(response, 'class="viz-plot"', count=8)
        self.assertContains(response, 'aria-current="page">Last 7 days')

    def test_the_list_links_to_it(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

        response = self.client.get(reverse("admin:fetch_fetchrun_changelist"))

        self.assertContains(response, f'href="{self.url}"')

    def test_needs_a_staff_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(User.objects.create_user(username="staff", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)
