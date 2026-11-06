"""Tests for the home page: its headline counts, and the samples of its feature blocks."""

from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.pages.cached_pages.home import INDIE_GENRE_ID, SAMPLE_ROWS, HomePageBuilder
from apps.streams.game_search import GameSearch
from apps.streams.models import Game, GameGenre, GameStats, GenreStats, StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch


class SearchWindowCountsTests(TestCase):
    def _streamer(self, host_user_id):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"login{host_user_id}",
            host_display_name=f"Display{host_user_id}",
        )

    def _search_row(self, profile, language, streams_count):
        return StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language=language,
            peak_viewers=10,
            avg_viewers=5,
            total_duration_seconds=3600,
            streams_count=streams_count,
            host_login=profile.host_login,
            host_display_name=profile.host_display_name,
        )

    def test_counts_each_streamer_once_and_every_stream(self):
        bilingual = self._streamer(1)
        self._search_row(bilingual, "en", 3)
        self._search_row(bilingual, "fr", 2)
        self._search_row(self._streamer(2), "de", 4)

        self.assertEqual(HomePageBuilder.search_window_counts(), (2, 9))

    # Every collected language is offered now, so the pages' list goes back to the
    # first four for a language collected but not offered yet.
    @mock.patch("apps.pages.cached_pages.home.PAGE_LANGUAGES", ("en", "fr", "de", "es"))
    def test_skips_languages_the_search_form_doesnt_offer_yet(self):
        self._search_row(self._streamer(1), "en", 3)
        self._search_row(self._streamer(2), "ja", 7)

        self.assertEqual(HomePageBuilder.search_window_counts(), (1, 3))

    def test_an_empty_search_table_counts_zero(self):
        self.assertEqual(HomePageBuilder.search_window_counts(), (0, 0))


class ShowcaseTests(TestCase):
    def setUp(self):
        # Process-cached; cleared so each test builds them from its own rows.
        GameSearch.get_filters_config.cache_clear()
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()
        self.next_id = 0

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _genre(self, host_genre_id, name):
        return GameGenre.objects.create(host_genre_id=host_genre_id, host_name=name, host_url="", slug=name.lower())

    def _genre_stats(self, genre, streams_count, language="en"):
        GenreStats.objects.create(genre=genre, language=language, streams_count=streams_count)

    def _search_row(self, genre_ids, peak_viewers):
        host_user_id = self._id()
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"login{host_user_id}",
            host_display_name=f"Display{host_user_id}",
        )
        return StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language="en",
            peak_viewers=peak_viewers,
            avg_viewers=50,
            total_duration_seconds=36000,
            streams_count=8,
            genre_ids=genre_ids,
            host_login=profile.host_login,
            host_display_name=profile.host_display_name,
        )

    def _indie_games(self, indie, year, count):
        for _ in range(count):
            number = self._id()
            game = Game.objects.create(
                host_game_id=number,
                host_name=f"Game {number}",
                category=Game.Category.ISGAME,
                release_date=date(year, 6, 1),
            )
            game.genres.set([indie])
            GameStats.objects.create(
                game=game, language="all", size_group=GameStats.ANY_SIZE, position=number, hours=[1], streams=[1],
            )

    @staticmethod
    def _showcase(year=2026, month=11):
        with mock.patch.object(timezone, "now", return_value=datetime(year, month, 5, 9, tzinfo=dt_timezone.utc)):
            return HomePageBuilder()._showcase()

    def test_the_streamers_sample_keeps_to_indie_highest_peak_first(self):
        self._genre(INDIE_GENRE_ID, "Indie")
        shooter = self._genre(5, "Shooter")
        rows = [self._search_row([INDIE_GENRE_ID], 100 + number) for number in range(SAMPLE_ROWS + 1)]
        other = self._search_row([shooter.host_genre_id], 150)

        sample = self._showcase()["streamers"]["rows"]

        self.assertEqual([row["login"] for row in sample], [row.host_login for row in reversed(rows[1:])])
        self.assertNotIn(other.host_login, [row["login"] for row in sample])

    def test_the_genre_sample_adds_indie_below_the_top_with_its_place(self):
        for number in range(SAMPLE_ROWS + 1):
            self._genre_stats(self._genre(number + 1, f"Genre {number}"), 1000 - number)
        indie = self._genre(INDIE_GENRE_ID, "Indie")
        self._genre_stats(indie, 300)
        self._genre_stats(indie, 200, language="de")

        rows = self._showcase()["genres"]["rows"]

        self.assertEqual(len(rows), SAMPLE_ROWS + 1)
        self.assertEqual(rows[-1], {"name": "Indie (#7 of 7)", "streams": 500, "marked": True})
        self.assertEqual([row["marked"] for row in rows[:-1]], [False] * SAMPLE_ROWS)

    def test_indie_among_the_biggest_genres_stays_in_its_place(self):
        self._genre_stats(self._genre(1, "Adventure"), 1000)
        self._genre_stats(self._genre(INDIE_GENRE_ID, "Indie"), 500)
        self._genre_stats(self._genre(2, "Puzzle"), 100)

        rows = self._showcase()["genres"]["rows"]

        self.assertEqual([row["name"] for row in rows], ["Adventure", "Indie (#2 of 3)", "Puzzle"])

    def test_the_games_sample_shows_this_years_indie_games(self):
        indie = self._genre(INDIE_GENRE_ID, "Indie")
        self._indie_games(indie, 2026, SAMPLE_ROWS)

        self._indie_games(indie, 2025, 1)

        games = self._showcase()["games"]

        self.assertEqual(len(games["rows"]), SAMPLE_ROWS)
        self.assertEqual({row["release_year"] for row in games["rows"]}, {2026})
        self.assertIn("released in 2026", games["sample_title"])

    def test_a_new_years_short_list_gives_way_to_last_years(self):
        indie = self._genre(INDIE_GENRE_ID, "Indie")
        self._indie_games(indie, 2026, SAMPLE_ROWS)
        self._indie_games(indie, 2027, SAMPLE_ROWS - 1)

        games = self._showcase(2027, 1)["games"]

        self.assertIn("released in 2026", games["sample_title"])
        self.assertEqual({row["release_year"] for row in games["rows"]}, {2026})

    def test_a_year_with_no_games_at_all_gives_way_to_last_years(self):
        self._indie_games(self._genre(INDIE_GENRE_ID, "Indie"), 2026, SAMPLE_ROWS)

        self.assertIn("released in 2026", self._showcase(2027, 1)["games"]["sample_title"])
