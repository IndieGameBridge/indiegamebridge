"""Tests for the fetch_twitch_streams management command.

The persistence loop in `_poll_streams_by_lang` is the highest-value thing to
test — it has real branching (get_or_create vs update, profile mismatch update,
dedup, snapshot append) and any regression silently corrupts data.
`_finalize_offline_streams` is exercised directly: stale streams must end up
OFFLINE with `max_viewers` and `host_game_ids` derived from `snapshots`, and streams
with too little data must be dropped.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.fetch.management.commands.fetch_twitch_streams import Command
from apps.fetch.models import FetchRun, FetchRunLanguage
from apps.streams.models import Game, Stream, StreamerProfile
from core.utils.twitch_api_client import StreamTuple


def _make_stream_tuple(**overrides):
    """Build a StreamTuple with all fields populated. IDs are numeric (int) post-boundary."""
    defaults = {
        "status": "live",
        "host_stream_id": 1001,
        "host_user_id": 2001,
        "host_login": "loginx",
        "host_display_name": "DisplayName",
        "host_game_id": 3001,
        "viewers": 100,
        "started_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return StreamTuple(**defaults)


def _build_command():
    cmd = Command()
    cmd.allowed_requests_per_language_poll_round = 1
    cmd.min_time_per_poll_round = 0
    cmd.stdout = mock.Mock()
    cmd.stderr = mock.Mock()
    return cmd


def _patch_iter_streams(*responses):
    """Patch TwitchApiClient so iter_streams returns the given responses in order.

    Each `response` is a tuple `(streams, cursor)`. After the list is exhausted,
    returns `([], None)` so the polling loop terminates cleanly.

    Returns the patcher context manager.
    """
    side_effect = list(responses) + [([], None)]
    patcher = mock.patch(
        "apps.fetch.management.commands.fetch_twitch_streams.TwitchApiClient"
    )
    mock_cls = patcher.start()
    instance = mock_cls.return_value
    instance.__enter__.return_value = instance
    instance.__exit__.return_value = False
    instance.iter_streams.side_effect = side_effect
    instance.requests_sent = 0
    return patcher, instance


class PollStreamsByLangPersistenceTests(TestCase):
    def setUp(self):
        self.command = _build_command()

    def _run(self, *responses):
        patcher, _ = _patch_iter_streams(*responses)
        try:
            self.command._poll_streams_by_lang(
                the_language="en", end_time_anchor=10**12
            )
        finally:
            patcher.stop()

    def test_skips_excluded_twitch_ids(self):
        excluded = _make_stream_tuple(host_user_id=2001, host_stream_id=1001)
        included = _make_stream_tuple(host_user_id=2002, host_stream_id=1002, host_login="keepme")
        patcher, _ = _patch_iter_streams(([excluded, included], None))
        try:
            self.command._poll_streams_by_lang(
                the_language="en",
                end_time_anchor=10**12,
                excluded_twitch_ids=frozenset({2001}),
            )
        finally:
            patcher.stop()

        # Opted-out streamer: neither a profile nor a stream is persisted.
        self.assertFalse(StreamerProfile.objects.filter(host_user_id=2001).exists())
        self.assertFalse(Stream.objects.filter(host_stream_id=1001).exists())
        # A non-excluded streamer in the same batch is still collected.
        self.assertTrue(StreamerProfile.objects.filter(host_user_id=2002).exists())
        self.assertTrue(Stream.objects.filter(host_stream_id=1002).exists())

    def test_creates_profile_and_stream_with_first_snapshot(self):
        st = _make_stream_tuple()
        self._run(([st], None))

        profile = StreamerProfile.objects.get(host_user_id=2001)
        self.assertEqual(profile.host, StreamerProfile.Host.TWITCH)
        self.assertEqual(profile.host_login, "loginx")
        self.assertEqual(profile.host_display_name, "DisplayName")

        stream = Stream.objects.get(host_stream_id=1001)
        self.assertEqual(stream.streamer_profile_id, profile.id)
        self.assertEqual(stream.status, Stream.Status.LIVE)
        self.assertEqual(stream.language, "en")

        self.assertEqual(len(stream.snapshots), 1)
        snap = stream.snapshots[0]
        self.assertEqual(snap["g"], 3001)
        self.assertEqual(snap["v"], 100)
        # The shared per-round timestamp is an int unix time; just sanity-check it.
        self.assertIsInstance(snap["t"], int)

    def test_existing_profile_with_changed_login_is_updated(self):
        StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="oldlogin",
            host_display_name="OldName",
        )

        st = _make_stream_tuple(host_login="newlogin", host_display_name="NewName")
        self._run(([st], None))

        profile = StreamerProfile.objects.get(host_user_id=2001)
        self.assertEqual(profile.host_login, "newlogin")
        self.assertEqual(profile.host_display_name, "NewName")
        self.assertEqual(StreamerProfile.objects.count(), 1)

    def test_existing_profile_unchanged_is_not_resaved(self):
        """If login/display_name match, no UPDATE should fire (avoids unnecessary writes)."""
        StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )
        before = StreamerProfile.objects.get(host_user_id=2001).updated_at

        st = _make_stream_tuple()
        self._run(([st], None))

        after = StreamerProfile.objects.get(host_user_id=2001).updated_at
        self.assertEqual(before, after)

    def test_dedup_within_poll_creates_one_set_of_rows(self):
        """Same host_stream_id appearing twice within a poll should yield one snapshot."""
        st = _make_stream_tuple()
        self._run(([st, st], None))

        self.assertEqual(StreamerProfile.objects.count(), 1)
        self.assertEqual(Stream.objects.count(), 1)
        self.assertEqual(len(Stream.objects.get().snapshots), 1)

    def test_existing_stream_finished_at_is_refreshed(self):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )
        old_finished_at = timezone.now() - timedelta(hours=1)
        stream = Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=1001,
            status=Stream.Status.LIVE,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=old_finished_at,
            snapshots=[],
        )

        st = _make_stream_tuple()
        self._run(([st], None))

        stream.refresh_from_db()
        self.assertEqual(stream.status, Stream.Status.LIVE)
        self.assertGreater(stream.finished_at, old_finished_at)
        self.assertEqual(Stream.objects.count(), 1)

    def test_each_poll_appends_a_snapshot_to_existing_stream(self):
        st = _make_stream_tuple()
        self._run(([st], None))
        self._run(([st], None))

        self.assertEqual(Stream.objects.count(), 1)
        self.assertEqual(len(Stream.objects.get().snapshots), 2)


class FinalizeOfflineStreamsTests(TestCase):
    """`_finalize_offline_streams` flips stale LIVE streams to OFFLINE, computing
    `max_viewers` and `host_game_ids` from each stream's `snapshots`. Streams that
    accumulated <= 1 snapshot are dropped entirely."""

    THRESHOLD_MINUTES = 100

    def setUp(self):
        self.command = _build_command()
        self.profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )

    def _make_stream(self, host_stream_id, status, finished_at, snapshots=None):
        return Stream.objects.create(
            streamer_profile=self.profile,
            host_stream_id=host_stream_id,
            status=status,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=finished_at,
            snapshots=snapshots or [],
        )

    def _run_finalize(self):
        threshold = timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES)
        return self.command._finalize_offline_streams(threshold)

    def test_stale_live_stream_is_finalized_with_summary_fields(self):
        stale = self._make_stream(
            host_stream_id=1,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 100, "v": 80,  "t": 1700000000},
                {"g": 100, "v": 120, "t": 1700000900},
                {"g": 200, "v": 50,  "t": 1700001800},
            ],
        )

        finalized, deleted = self._run_finalize()

        stale.refresh_from_db()
        self.assertEqual((finalized, deleted), (1, 0))
        self.assertEqual(stale.status, Stream.Status.OFFLINE)
        self.assertEqual(stale.max_viewers, 120)
        # mean of 80, 120, 50 = 83.33 -> rounded to 83
        self.assertEqual(stale.avg_viewers, 83)
        self.assertEqual(stale.host_game_ids, [100, 200])

    def test_fresh_live_stream_is_left_alone(self):
        fresh = self._make_stream(
            host_stream_id=2,
            status=Stream.Status.LIVE,
            finished_at=timezone.now(),
            snapshots=[
                {"g": 100, "v": 80, "t": 1700000000},
                {"g": 100, "v": 90, "t": 1700000900},
            ],
        )

        finalized, deleted = self._run_finalize()

        fresh.refresh_from_db()
        self.assertEqual((finalized, deleted), (0, 0))
        self.assertEqual(fresh.status, Stream.Status.LIVE)
        self.assertEqual(fresh.max_viewers, 0)
        self.assertEqual(fresh.avg_viewers, 0)
        self.assertEqual(fresh.host_game_ids, [])

    def test_already_offline_stream_is_untouched(self):
        old_offline = self._make_stream(
            host_stream_id=3,
            status=Stream.Status.OFFLINE,
            finished_at=timezone.now() - timedelta(days=7),
            snapshots=[],
        )

        finalized, deleted = self._run_finalize()

        old_offline.refresh_from_db()
        self.assertEqual((finalized, deleted), (0, 0))
        self.assertEqual(old_offline.status, Stream.Status.OFFLINE)

    def test_finished_at_is_preserved(self):
        """finished_at represents the actual end time and must stay frozen at finalize."""
        stale = self._make_stream(
            host_stream_id=4,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 100, "v": 50, "t": 1700000000},
                {"g": 100, "v": 60, "t": 1700000900},
            ],
        )
        original_finished_at = stale.finished_at

        self._run_finalize()

        stale.refresh_from_db()
        self.assertEqual(stale.status, Stream.Status.OFFLINE)
        self.assertEqual(stale.finished_at, original_finished_at)

    def test_stream_with_single_snapshot_is_deleted(self):
        single = self._make_stream(
            host_stream_id=5,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[{"g": 100, "v": 50, "t": 1700000000}],
        )

        finalized, deleted = self._run_finalize()

        self.assertEqual((finalized, deleted), (0, 1))
        self.assertFalse(Stream.objects.filter(pk=single.pk).exists())

    def test_stream_with_zero_snapshots_is_deleted(self):
        empty = self._make_stream(
            host_stream_id=6,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[],
        )

        finalized, deleted = self._run_finalize()

        self.assertEqual((finalized, deleted), (0, 1))
        self.assertFalse(Stream.objects.filter(pk=empty.pk).exists())

    def test_mixed_batch_finalizes_some_and_deletes_others(self):
        ok = self._make_stream(
            host_stream_id=7,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 100, "v": 80, "t": 1700000000},
                {"g": 100, "v": 90, "t": 1700000900},
            ],
        )
        single = self._make_stream(
            host_stream_id=8,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[{"g": 200, "v": 50, "t": 1700000000}],
        )

        finalized, deleted = self._run_finalize()

        ok.refresh_from_db()
        self.assertEqual((finalized, deleted), (1, 1))
        self.assertEqual(ok.status, Stream.Status.OFFLINE)
        self.assertEqual(ok.max_viewers, 90)
        # mean of 80, 90 = 85
        self.assertEqual(ok.avg_viewers, 85)
        self.assertEqual(ok.host_game_ids, [100])
        self.assertFalse(Stream.objects.filter(pk=single.pk).exists())

    def test_placeholder_games_are_inserted_for_finalized_streams(self):
        """Each unique host_game_id observed across just-finalized streams gets
        a placeholder Game row. These rows feed the deferred IGDB enrichment."""
        self._make_stream(
            host_stream_id=10,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 500, "v": 10, "t": 1700000000},
                {"g": 500, "v": 12, "t": 1700000900},
                {"g": 600, "v": 20, "t": 1700001800},
            ],
        )

        self._run_finalize()

        game_ids = sorted(Game.objects.values_list("host_game_id", flat=True))
        self.assertEqual(game_ids, [500, 600])
        # Placeholders carry no metadata until enrichment runs.
        for game in Game.objects.all():
            self.assertEqual(game.host_name, "")
            self.assertEqual(game.host_summary, "")
            self.assertEqual(game.host_url, "")
            self.assertEqual(game.genres.count(), 0)

    def test_placeholder_game_insert_skips_already_existing_rows(self):
        """ignore_conflicts must keep the existing row intact rather than raising
        or overwriting; pre-enriched data must survive a re-finalization."""
        Game.objects.create(host_game_id=500, host_name="Already Enriched")

        self._make_stream(
            host_stream_id=11,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 500, "v": 10, "t": 1700000000},
                {"g": 600, "v": 20, "t": 1700000900},
            ],
        )

        self._run_finalize()

        self.assertEqual(Game.objects.count(), 2)
        existing = Game.objects.get(host_game_id=500)
        self.assertEqual(existing.host_name, "Already Enriched")
        self.assertTrue(Game.objects.filter(host_game_id=600).exists())

    def test_dropped_streams_do_not_produce_placeholder_games(self):
        """Streams dropped for insufficient snapshots never get host_game_ids
        finalized, so their game ids must not leak into the Game table."""
        self._make_stream(
            host_stream_id=12,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[{"g": 700, "v": 50, "t": 1700000000}],
        )

        self._run_finalize()

        self.assertFalse(Game.objects.filter(host_game_id=700).exists())

    def test_low_viewer_streams_do_not_produce_placeholder_games(self):
        """max_viewers < 3 drops the stream, so its game ids must not get rows."""
        self._make_stream(
            host_stream_id=13,
            status=Stream.Status.LIVE,
            finished_at=timezone.now() - timedelta(minutes=self.THRESHOLD_MINUTES + 1),
            snapshots=[
                {"g": 800, "v": 1, "t": 1700000000},
                {"g": 800, "v": 2, "t": 1700000900},
            ],
        )

        self._run_finalize()

        self.assertFalse(Game.objects.filter(host_game_id=800).exists())


class PollStatsTests(TestCase):
    """What `_poll_streams_by_lang` records about a language's polling."""

    def setUp(self):
        self.command = _build_command()

    def _poll(self, *responses, end_time_anchor=10**12, excluded_twitch_ids=frozenset()):
        patcher, _ = _patch_iter_streams(*responses)
        try:
            return self.command._poll_streams_by_lang(
                the_language="en",
                end_time_anchor=end_time_anchor,
                excluded_twitch_ids=excluded_twitch_ids,
                stats=FetchRunLanguage(language="en"),
            )
        finally:
            patcher.stop()

    def test_counts_what_each_fetched_stream_came_to(self):
        excluded = _make_stream_tuple(host_user_id=2001, host_stream_id=1001)
        new = _make_stream_tuple(host_user_id=2002, host_stream_id=1002)
        other = _make_stream_tuple(host_user_id=2003, host_stream_id=1003)

        stats = self._poll(([excluded, new, new, other], None), excluded_twitch_ids=frozenset({2001}))

        self.assertEqual(
            (stats.streams_fetched, stats.streams_excluded, stats.streams_duplicates, stats.streams_written),
            (4, 1, 1, 2),
        )
        self.assertEqual((stats.streams_created, stats.profiles_created), (2, 2))

    def test_streams_and_streamers_seen_before_are_written_not_created(self):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )
        Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=1001,
            status=Stream.Status.LIVE,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now(),
            snapshots=[],
        )

        stats = self._poll(([_make_stream_tuple()], None))

        self.assertEqual((stats.streams_written, stats.streams_created, stats.profiles_created), (1, 0, 0))

    def test_each_round_adds_up_and_is_recorded(self):
        patcher, client = _patch_iter_streams()
        responses = [
            ([_make_stream_tuple(host_stream_id=1001)], "cursor-1"),
            ([_make_stream_tuple(host_stream_id=1002, host_user_id=2002)], None),
        ]

        def iter_streams(**kwargs):
            # As paging through two pages would
            client.requests_sent += 2
            return responses.pop(0)

        client.iter_streams.side_effect = iter_streams
        try:
            stats = self.command._poll_streams_by_lang(the_language="en", end_time_anchor=10**12)
        finally:
            patcher.stop()

        self.assertEqual((stats.rounds, stats.requests, stats.streams_written), (2, 4, 2))
        self.assertEqual([one_round["requests"] for one_round in stats.rounds_detail], [2, 2])
        self.assertEqual([one_round["written"] for one_round in stats.rounds_detail], [1, 1])

    def test_stopping_at_the_time_limit_is_recorded(self):
        stats = self._poll(([_make_stream_tuple()], "more-pages"), end_time_anchor=0)

        self.assertTrue(stats.time_limit_hit)

    def test_running_out_of_pages_is_not_the_time_limit(self):
        stats = self._poll(([_make_stream_tuple()], None), end_time_anchor=0)

        self.assertFalse(stats.time_limit_hit)

    def test_a_round_that_raises_leaves_the_rounds_before_it(self):
        patcher, client = _patch_iter_streams()
        client.iter_streams.side_effect = [
            ([_make_stream_tuple()], "cursor-1"),
            RuntimeError("Helix down"),
        ]
        stats = FetchRunLanguage(language="en")
        try:
            with self.assertRaises(RuntimeError):
                self.command._poll_streams_by_lang(the_language="en", end_time_anchor=10**12, stats=stats)
        finally:
            patcher.stop()

        self.assertEqual((stats.rounds, stats.streams_written), (1, 1))


def _poll_one_round(the_language, end_time_anchor, excluded_twitch_ids, stats):
    """Stands in for a language's polling thread. It mustn't touch the database:
    the test's transaction isn't visible from other threads."""
    stats.add_round(
        requests=3, fetched=5, excluded=1, duplicates=1, created=2, profiles_created=1,
        helix_seconds=0.5, write_seconds=0.25,
    )
    return stats


class FetchRunRecordingTests(TestCase):
    """`handle` records each run, with a row per language, for the admin."""

    def setUp(self):
        self.profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=2001,
            host_login="loginx",
            host_display_name="DisplayName",
        )
        self.next_host_stream_id = 1000

    def _ended_stream(self, snapshots):
        self.next_host_stream_id += 1
        return Stream.objects.create(
            streamer_profile=self.profile,
            host_stream_id=self.next_host_stream_id,
            status=Stream.Status.LIVE,
            language="en",
            started_at=timezone.now() - timedelta(hours=4),
            finished_at=timezone.now() - timedelta(hours=2),
            snapshots=snapshots,
        )

    def _fetch(self, poll):
        with (
            mock.patch.object(Command, "_poll_streams_by_lang", side_effect=poll),
            self.assertLogs("apps.fetch", level="INFO"),
        ):
            call_command("fetch_twitch_streams", stdout=StringIO())

    def test_a_run_is_recorded_with_a_row_per_language(self):
        self._ended_stream([{"g": 1, "v": 10, "t": 1700000000}, {"g": 1, "v": 12, "t": 1700000900}])
        self._ended_stream([{"g": 1, "v": 10, "t": 1700000000}])

        self._fetch(_poll_one_round)

        run = FetchRun.objects.get()
        self.assertEqual(run.status, FetchRun.Status.SUCCEEDED)
        self.assertIsNotNone(run.finished_at)
        self.assertGreaterEqual(run.duration_seconds, 0)
        # 4 languages, each writing 3 of the 5 streams it fetched
        self.assertEqual(run.streams_collected, 12)
        self.assertEqual((run.streams_finalized, run.streams_dropped), (1, 1))
        self.assertIsNotNone(run.finalize_seconds)
        self.assertFalse(run.time_limit_hit)

        self.assertCountEqual(run.languages.values_list("language", flat=True), ["en", "de", "fr", "es"])
        en = run.languages.get(language="en")
        self.assertEqual(
            (en.rounds, en.requests, en.streams_written, en.streams_created, en.profiles_created),
            (1, 3, 3, 2, 1),
        )
        self.assertIsNotNone(en.duration_seconds)
        self.assertEqual(en.error, "")

    def test_a_language_that_raises_fails_the_run_but_not_the_other_languages(self):
        def poll(the_language, end_time_anchor, excluded_twitch_ids, stats):
            _poll_one_round(the_language, end_time_anchor, excluded_twitch_ids, stats)
            if the_language == "de":
                raise RuntimeError("Helix down")
            return stats

        self._fetch(poll)

        run = FetchRun.objects.get()
        self.assertEqual(run.status, FetchRun.Status.FAILED)
        self.assertEqual(run.error, "")
        de = run.languages.get(language="de")
        self.assertEqual(de.error, "RuntimeError: Helix down")
        # What it wrote before raising still counts
        self.assertEqual(de.streams_written, 3)
        self.assertEqual(run.streams_collected, 12)
        self.assertFalse(run.languages.exclude(language="de").exclude(error="").exists())

    def test_a_language_stopped_at_the_time_limit_marks_the_run(self):
        def poll(the_language, end_time_anchor, excluded_twitch_ids, stats):
            stats.time_limit_hit = the_language == "en"
            return stats

        self._fetch(poll)

        run = FetchRun.objects.get()
        self.assertTrue(run.time_limit_hit)
        self.assertEqual(run.status, FetchRun.Status.SUCCEEDED)

    def test_a_failure_outside_the_languages_is_recorded_and_raised(self):
        with mock.patch.object(Command, "_finalize_offline_streams", side_effect=RuntimeError("database gone")):
            with self.assertRaises(RuntimeError):
                self._fetch(_poll_one_round)

        run = FetchRun.objects.get()
        self.assertEqual(run.status, FetchRun.Status.FAILED)
        self.assertEqual(run.error, "RuntimeError: database gone")
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.languages.count(), 4)
