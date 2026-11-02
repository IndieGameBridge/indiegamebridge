"""Tests for the admin's Job runs > Graphs page."""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.fetch.models import FetchRun
from apps.jobs.cron import JOBS
from apps.jobs.graphs import FIRST_COUNT, job_graphs
from apps.jobs.models import JobRun

User = get_user_model()

# Thursday noon, UTC.
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=dt_timezone.utc)


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


def _figure(context, key):
    return next(figure for figure in context["figures"] if figure.key == key)


class AllJobsTests(TestCase):
    def _rows(self, context):
        return {row[0].text: row for row in _figure(context, "jobs").table_rows}

    def test_nothing_recorded_yet(self):
        context = job_graphs(14, now=NOW)

        self.assertNotIn("figures", context)
        self.assertEqual(context["empty_text"], "No job runs are recorded yet.")

    def test_lists_every_job_fetch_first(self):
        _run("approve_streams", NOW - timedelta(minutes=10))

        rows = _figure(job_graphs(14, now=NOW), "jobs").table_rows

        self.assertEqual([row[0].text for row in rows], ["fetch_twitch_streams", *(job.name for job in JOBS)])
        self.assertEqual(rows[2][0].url, "?job=approve_streams&days=14")

    def test_a_job_whose_latest_run_is_late_is_overdue(self):
        _fetch_run(NOW - timedelta(minutes=10))
        # Hourly, so late after 75 minutes.
        _run("approve_streams", NOW - timedelta(minutes=80))
        _run("rebuild_search_stats", NOW - timedelta(minutes=30))

        context = job_graphs(14, now=NOW)
        rows = self._rows(context)

        self.assertEqual(rows["approve_streams"][6].text, "80 min ago, overdue")
        self.assertEqual(rows["approve_streams"][6].marker, "warning")
        self.assertEqual(rows["rebuild_search_stats"][6].text, "30 min ago")
        self.assertEqual(rows["fetch_twitch_streams"][7].text, "Succeeded, 3m 00s")
        # One that never ran is late once its first run is: from when recording began.
        self.assertEqual(rows["categorize_games"][6].text, "None yet, overdue")
        self.assertEqual(rows["update_cached_pages"][6].text, "None yet")
        tiles = {tile.label: tile for tile in context["tiles"]}
        # approve_streams, and the hourly jobs that never ran: too many to name in the tile.
        self.assertEqual((tiles["Overdue jobs"].value, tiles["Overdue jobs"].note), ("3", ""))

    def test_names_the_overdue_jobs_when_few(self):
        _fetch_run(NOW - timedelta(minutes=10))
        for job in JOBS:
            _run(job.name, NOW - timedelta(minutes=80 if job.name == "approve_streams" else 10))

        tiles = {tile.label: tile for tile in job_graphs(14, now=NOW)["tiles"]}

        self.assertEqual((tiles["Overdue jobs"].value, tiles["Overdue jobs"].note), ("1", "approve_streams"))

    def test_counts_the_failed_and_the_never_finished(self):
        _run("archive_streams", NOW - timedelta(days=2), status=JobRun.Status.FAILED, error="CommandError: boom")
        # Killed: still RUNNING five hours on.
        _run("archive_streams", NOW - timedelta(hours=5), duration=None, status=JobRun.Status.RUNNING)
        # Still going: left out.
        _run("archive_streams", NOW - timedelta(minutes=5), duration=None, status=JobRun.Status.RUNNING)

        context = job_graphs(14, now=NOW)
        row = self._rows(context)["archive_streams"]

        self.assertEqual([row[2].text, row[3].text, row[3].marker], ["2", "2", "critical"])
        self.assertIn("status__exact=failed", row[3].url)
        self.assertEqual(row[7].text, "Running now")
        tiles = {tile.label: tile for tile in context["tiles"]}
        self.assertEqual(tiles["Failed"].value, "2")
        self.assertEqual(tiles["Failed"].note, "1 never finished")

    def test_offers_a_recorded_job_cron_doesnt_list(self):
        _run("backfill_stream_duration", NOW - timedelta(hours=1))

        select = job_graphs(14, job="nope", now=NOW)["select"]

        self.assertEqual(select["options"][-1]["value"], "backfill_stream_duration")
        # An unknown job shows them all.
        self.assertTrue(select["options"][0]["selected"])


class OneJobTests(TestCase):
    def test_nothing_recorded_for_it_yet(self):
        _run("approve_streams", NOW - timedelta(minutes=10))

        context = job_graphs(14, job="archive_streams", now=NOW)

        self.assertEqual(context["empty_text"], "No runs of archive_streams are recorded yet.")

    def _approvals(self):
        # Hourly at :55, from 03:55.
        start = NOW - timedelta(hours=8, minutes=5)
        for index in range(9):
            # The 06:55 and 07:55 runs are missing: the line breaks there.
            if index in (3, 4):
                continue
            failed = index == 1
            _run(
                "approve_streams", start + index * timedelta(hours=1), duration=40 + index,
                status=JobRun.Status.FAILED if failed else JobRun.Status.SUCCEEDED,
                error="OperationalError: server closed the connection" if failed else "",
                counts={"approved": 10, "deleted": 1},
            )

    def test_a_job_run_more_often_than_daily_gets_a_point_for_each_run(self):
        self._approvals()

        context = job_graphs(14, job="approve_streams", now=NOW)

        runs, days = context["hover_sources"]
        self.assertEqual(len(runs.rows), 7)
        self.assertEqual(runs.rows[1]["values"][:2], ["41s", "Failed. OperationalError: server closed the connection"])
        plot = _figure(context, "run-time").plots[0]
        self.assertEqual(plot.lines[0].path.count("M"), 2)
        self.assertEqual([marker.kind for marker in plot.markers], ["critical"])
        # A day's totals of the counts follow its time, runs and failures.
        self.assertEqual(days.rows[-1]["values"][FIRST_COUNT:], ["70", "7"])
        self.assertEqual(days.rows[-1]["title"], "Thu 29 Oct, so far")
        self.assertEqual(len(_figure(context, "counts").plots), 2)

    def test_tiles_count_runs_failures_and_the_missing(self):
        self._approvals()

        tiles = {tile.label: tile for tile in job_graphs(14, job="approve_streams", now=NOW)["tiles"]}

        self.assertEqual((tiles["Runs"].value, tiles["Runs"].note), ("7", "2 missing"))
        self.assertEqual(tiles["Failed"].value, "1")
        self.assertEqual(tiles["Longest run"].value, "48s")
        self.assertEqual(tiles["Latest run"].value, "5 min ago")
        self.assertEqual(tiles["Streams approved"].value, "70")

    def test_a_daily_job_gets_a_column_for_each_day(self):
        _run("update_cached_pages", NOW - timedelta(days=1, hours=3), duration=90, counts={"pages": 12})
        _run("update_cached_pages", NOW - timedelta(days=1, hours=1), duration=30, counts={"pages": 1}, arguments="home")

        context = job_graphs(14, job="update_cached_pages", now=NOW)

        [days] = context["hover_sources"]
        self.assertEqual(days.rows[-2]["values"], ["2m 00s", "2 runs", None, "13"])
        self.assertEqual(days.rows[-1]["values"], [None, "0 runs", None, "0"])
        plot = _figure(context, "run-time").plots[0]
        self.assertEqual([len(column.parts) for column in plot.columns], [1, 0])
        late = {tile.label: tile for tile in context["tiles"]}["Latest run"]
        self.assertEqual((late.value, late.note), ("25 h ago", "Succeeded, 30s"))


class JobGraphsPageTests(TestCase):
    def setUp(self):
        _run("approve_streams", timezone.now() - timedelta(minutes=10), counts={"approved": 3, "deleted": 1})
        self.url = reverse("admin:jobs_jobrun_graphs")

    def _admin(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password="unused"))

    def test_renders_the_table_of_jobs(self):
        self._admin()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th scope="row"><a href="?job=approve_streams&amp;days=14">approve_streams</a></th>', html=True)
        self.assertNotContains(response, 'class="viz-plot"')

    def test_renders_a_jobs_graphs(self):
        self._admin()

        response = self.client.get(self.url, {"job": "approve_streams", "days": "7"})

        # Run time, then the two counts.
        self.assertContains(response, 'class="viz-plot"', count=3)
        self.assertContains(response, '<option value="approve_streams" selected>approve_streams</option>', html=True)
        # The time ranges keep the job.
        self.assertContains(response, 'href="?job=approve_streams&amp;days=30"')

    def test_a_runs_page_shows_what_it_did(self):
        self._admin()
        run = JobRun.objects.get()

        response = self.client.get(reverse("admin:jobs_jobrun_change", args=[run.pk]))

        self.assertContains(response, "Streams approved: 3; Streams deleted, no game played: 1")

    def test_the_list_links_to_it(self):
        self._admin()

        response = self.client.get(reverse("admin:jobs_jobrun_changelist"), {"job": "approve_streams"})

        self.assertContains(response, f'href="{self.url}"')

    def test_needs_a_staff_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(User.objects.create_user(username="staff", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)
