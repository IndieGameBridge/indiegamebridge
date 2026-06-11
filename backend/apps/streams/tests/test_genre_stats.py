"""Tests for the per-genre stats read-model behind the Genre Trends page.

rebuild_genre_stats walks streamers in chunks, accumulating each chunk's contribution
into GenreStats draft counters, then publishes draft -> published when the cursor wraps
past the end of the set (one full pass = one cycle). Covered here:

  - streams/streamers per genre come from each stream's distinct genre_ids, and a
    multi-genre stream counts toward each of its genres;
  - hours per genre split a stream's real duration by snapshot share, with non-game
    (ungenred) snapshots - e.g. Just Chatting - contributing nothing;
  - streams outside the 4-week window are ignored;
  - distinct streamers sum correctly when a cycle spans several chunks;
  - published values only change at the end of a cycle, not mid-build.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.streams.models import (
    Game,
    GameGenre,
    GenreStats,
    Stream,
    StreamerProfile,
)


class RebuildGenreStatsTests(TestCase):
    def _make_genre(self, host_genre_id, name):
        return GameGenre.objects.create(
            host_genre_id=host_genre_id,
            host_name=name,
            host_url="",
            slug=name.lower(),
        )

    def _make_game(self, host_game_id, genres):
        game = Game.objects.create(host_game_id=host_game_id)
        game.genres.set(genres)
        return game

    def _make_streamer(self, host_user_id, login):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _make_stream(self, profile, host_stream_id, duration, genre_ids,
                     snapshots=None, days_ago=1):
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=host_stream_id,
            status=Stream.Status.APPROVED,
            language="en",
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=days_ago),
            snapshots=snapshots or [],
            max_viewers=50,
            avg_viewers=20,
            duration=duration,
            genre_ids=genre_ids,
        )

    def _run_full_cycle(self, chunk=20000):
        # reset zeroes the draft + cursor and processes the first chunk; repeated
        # runs cover the rest; the run that finds nothing past the cursor publishes
        # the draft and wraps. A final empty run guarantees we land on that publish.
        call_command("rebuild_genre_stats", reset=True, chunk=chunk)
        for _ in range(50):
            if not StreamerProfile.objects.filter(
                id__gt=self._cursor()
            ).exists():
                break
            call_command("rebuild_genre_stats", chunk=chunk)
        call_command("rebuild_genre_stats", chunk=chunk)  # publish + wrap

    @staticmethod
    def _cursor():
        from apps.streams.models import GenreStatsBuildState
        state = GenreStatsBuildState.objects.filter(pk=1).first()
        return state.last_profile_id if state else 0

    @staticmethod
    def _stats(host_genre_id):
        return GenreStats.objects.get(genre__host_genre_id=host_genre_id)

    def test_streams_and_streamers_count_per_genre(self):
        self._make_genre(10, "Action")
        self._make_genre(20, "Puzzle")
        s1 = self._make_streamer(1, "s1")
        s2 = self._make_streamer(2, "s2")
        # s1 plays a multi-genre stream (counts toward both 10 and 20).
        self._make_stream(s1, 1, duration=3600, genre_ids=[10, 20])
        self._make_stream(s2, 2, duration=3600, genre_ids=[10])

        self._run_full_cycle()

        action = self._stats(10)
        puzzle = self._stats(20)
        self.assertEqual((action.streams_count, action.streamers_count), (2, 2))
        self.assertEqual((puzzle.streams_count, puzzle.streamers_count), (1, 1))

    def test_duration_split_by_snapshot_share_excludes_ungenred(self):
        action = self._make_genre(10, "Action")
        self._make_game(host_game_id=100, genres=[action])
        streamer = self._make_streamer(1, "solo")
        # 1h stream: 2 snapshots on the Action game, 2 on an ungenred category
        # (e.g. Just Chatting, game id 999 with no genre mapping). Action's share is
        # 2/4 of 3600s = 1800s; the ungenred half contributes nothing.
        self._make_stream(
            streamer, 1, duration=3600, genre_ids=[10],
            snapshots=[{"g": 100}, {"g": 100}, {"g": 999}, {"g": 999}],
        )

        self._run_full_cycle()

        self.assertEqual(self._stats(10).total_duration_seconds, 1800)

    def test_streams_outside_window_ignored(self):
        self._make_genre(10, "Action")
        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, duration=3600, genre_ids=[10], days_ago=40)

        self._run_full_cycle()

        self.assertFalse(GenreStats.objects.filter(
            genre__host_genre_id=10
        ).exclude(streams_count=0).exists())

    def test_distinct_streamers_sum_across_chunks(self):
        self._make_genre(10, "Action")
        self._make_stream(self._make_streamer(1, "a"), 1, duration=3600, genre_ids=[10])
        self._make_stream(self._make_streamer(2, "b"), 2, duration=3600, genre_ids=[10])

        # chunk=1 forces each streamer into its own chunk; the per-chunk distinct
        # counts must still sum to 2 since chunks partition the streamer set.
        self._run_full_cycle(chunk=1)

        action = self._stats(10)
        self.assertEqual((action.streams_count, action.streamers_count), (2, 2))

    def test_published_only_after_cycle_completes(self):
        self._make_genre(10, "Action")
        self._make_stream(self._make_streamer(1, "solo"), 1, duration=3600, genre_ids=[10])

        # First chunk accumulates into the draft but must not touch published values.
        call_command("rebuild_genre_stats", reset=True)
        mid = self._stats(10)
        self.assertEqual(mid.streams_count, 0)
        self.assertEqual(mid.draft_streams_count, 1)

        # The wrapping run publishes and zeroes the draft.
        call_command("rebuild_genre_stats")
        done = self._stats(10)
        self.assertEqual(done.streams_count, 1)
        self.assertEqual(done.draft_streams_count, 0)
        self.assertIsNotNone(done.computed_at)
