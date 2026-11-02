"""Tests for the per-genre stats read-model behind the Genre Trends page.

rebuild_genre_stats recomputes every genre and language in one pass and replaces the
table's rows. Covered here:

  - streams/streamers per genre come from each stream's distinct genre_ids, and a
    multi-genre stream counts toward each of its genres;
  - hours per genre split a stream's real duration by snapshot share, with non-game
    (ungenred) snapshots - e.g. Just Chatting - contributing nothing;
  - streams outside the 4-week window are ignored, and a rebuild drops the numbers
    of streams that have left it;
  - a streamer counts once per genre, however many streams they made.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO

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
                     snapshots=None, days_ago=1, language="en"):
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=host_stream_id,
            status=Stream.Status.APPROVED,
            language=language,
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=days_ago),
            snapshots=snapshots or [],
            max_viewers=50,
            avg_viewers=20,
            duration=duration,
            genre_ids=genre_ids,
        )

    def _rebuild(self):
        call_command("rebuild_genre_stats", stdout=StringIO())

    @staticmethod
    def _stats(host_genre_id, language="en"):
        return GenreStats.objects.get(
            genre__host_genre_id=host_genre_id, language=language
        )

    def test_streams_and_streamers_count_per_genre(self):
        self._make_genre(10, "Action")
        self._make_genre(20, "Puzzle")
        s1 = self._make_streamer(1, "s1")
        s2 = self._make_streamer(2, "s2")
        # s1 plays a multi-genre stream (counts toward both 10 and 20).
        self._make_stream(s1, 1, duration=3600, genre_ids=[10, 20])
        self._make_stream(s2, 2, duration=3600, genre_ids=[10])

        self._rebuild()

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

        self._rebuild()

        self.assertEqual(self._stats(10).total_duration_seconds, 1800)

    def test_streams_outside_window_ignored(self):
        self._make_genre(10, "Action")
        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, duration=3600, genre_ids=[10], days_ago=40)

        self._rebuild()

        self.assertFalse(GenreStats.objects.filter(
            genre__host_genre_id=10
        ).exclude(streams_count=0).exists())

    def test_a_streamer_counts_once_per_genre(self):
        self._make_genre(10, "Action")
        regular = self._make_streamer(1, "regular")
        self._make_stream(regular, 1, duration=3600, genre_ids=[10])
        self._make_stream(regular, 2, duration=3600, genre_ids=[10])
        self._make_stream(self._make_streamer(2, "once"), 3, duration=3600, genre_ids=[10])

        self._rebuild()

        action = self._stats(10)
        self.assertEqual((action.streams_count, action.streamers_count), (3, 2))

    def test_counts_split_by_language(self):
        self._make_genre(10, "Action")
        en = self._make_streamer(1, "en_streamer")
        fr = self._make_streamer(2, "fr_streamer")
        es = self._make_streamer(3, "es_streamer")
        # Two English streams + one French + one Spanish stream on the same genre.
        self._make_stream(en, 1, duration=3600, genre_ids=[10], language="en")
        self._make_stream(en, 2, duration=3600, genre_ids=[10], language="en")
        self._make_stream(fr, 3, duration=3600, genre_ids=[10], language="fr")
        self._make_stream(es, 4, duration=3600, genre_ids=[10], language="es")

        self._rebuild()

        self.assertEqual(self._stats(10, "en").streams_count, 2)
        self.assertEqual(self._stats(10, "en").streamers_count, 1)
        self.assertEqual(self._stats(10, "fr").streams_count, 1)
        self.assertEqual(self._stats(10, "fr").streamers_count, 1)
        self.assertEqual(self._stats(10, "es").streams_count, 1)
        self.assertEqual(self._stats(10, "es").streamers_count, 1)

    def test_a_language_collected_before_the_page_shows_it_is_counted(self):
        self._make_genre(10, "Action")
        self._make_stream(self._make_streamer(1, "ja_streamer"), 1, duration=3600, genre_ids=[10], language="ja")

        self._rebuild()

        self.assertEqual(self._stats(10, "ja").streams_count, 1)

    def test_unlisted_language_is_ignored(self):
        self._make_genre(10, "Action")
        streamer = self._make_streamer(1, "ru_streamer")
        # Russian isn't a language the fetch collects, so it contributes no rows.
        self._make_stream(streamer, 1, duration=3600, genre_ids=[10], language="ru")

        self._rebuild()

        self.assertFalse(
            GenreStats.objects.filter(genre__host_genre_id=10)
            .exclude(streams_count=0)
            .exists()
        )

    def test_a_rebuild_replaces_the_previous_numbers(self):
        self._make_genre(10, "Action")
        self._make_genre(20, "Puzzle")
        streamer = self._make_streamer(1, "solo")
        stream = self._make_stream(streamer, 1, duration=3600, genre_ids=[10])
        self._rebuild()
        self.assertEqual(self._stats(10).streams_count, 1)
        self.assertIsNotNone(self._stats(10).computed_at)

        # The Action stream leaves the window; a Puzzle one comes in.
        stream.finished_at = timezone.now() - timedelta(days=40)
        stream.save(update_fields=["finished_at"])
        self._make_stream(streamer, 2, duration=3600, genre_ids=[20])
        self._rebuild()

        self.assertFalse(GenreStats.objects.filter(genre__host_genre_id=10).exists())
        self.assertEqual(self._stats(20).streams_count, 1)

    def test_a_snapshot_on_a_game_of_two_genres_counts_for_both(self):
        action = self._make_genre(10, "Action")
        puzzle = self._make_genre(20, "Puzzle")
        self._make_game(host_game_id=100, genres=[action, puzzle])
        self._make_stream(
            self._make_streamer(1, "solo"), 1, duration=3600, genre_ids=[10, 20],
            snapshots=[{"g": 100}, {"g": 100}, {"g": 100}],
        )

        self._rebuild()

        self.assertEqual((self._stats(10).total_duration_seconds, self._stats(20).total_duration_seconds), (3600, 3600))
