"""Tests for the Games page's read model, its search and its API.

rebuild_game_stats counts the streams live in each hour of the last 4 weeks, per game,
language and streamer size, and stores each list's order. Covered here:

  - a stream counts once in each hour it was seen on a game, whatever its status;
  - only games count, and only the 4 weeks' whole hours;
  - each size group holds its own streamers, a streamer with no size counts under any
    size only, and all languages adds the languages up;
  - the sort: the newest hour decides, and an older hour only breaks a tie;
  - GameSearch reads one stored list, narrowed by genre and release year.
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.streams.game_search import GameSearch
from apps.streams.languages import ALL_LANGUAGES
from apps.streams.management.commands.rebuild_game_stats import WINDOW_HOURS
from apps.streams.models import (
    Game,
    GameGenre,
    GameStats,
    Stream,
    StreamerProfile,
    StreamerSearchStats,
)

NOW = datetime(2026, 11, 3, 10, 30, tzinfo=dt_timezone.utc)
# The newest whole hour at NOW: 09:00 to 10:00.
NEWEST_HOUR = int(NOW.timestamp()) // 3600 - 1


class GameStatsTestCase(TestCase):
    def setUp(self):
        # Process-cached; cleared so each test builds it from its own rows.
        GameSearch.get_filters_config.cache_clear()
        cache.clear()  # the throttle counters live there
        self.next_id = 0

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _game(self, name="", category=Game.Category.ISGAME, genres=(), release_date=None):
        game = Game.objects.create(host_game_id=self._id(), host_name=name, category=category, release_date=release_date)
        game.genres.set(genres)
        return game

    def _genre(self, host_genre_id, name):
        return GameGenre.objects.create(host_genre_id=host_genre_id, host_name=name, host_url="", slug=name.lower())

    def _streamer(self, peak=None, language="en"):
        profile_id = self._id()
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=profile_id,
            host_login=f"login{profile_id}",
            host_display_name=f"Display{profile_id}",
        )
        if peak is not None:
            StreamerSearchStats.objects.create(
                streamer_profile=profile,
                language=language,
                peak_viewers=peak,
                avg_viewers=5,
                total_duration_seconds=3600,
                streams_count=1,
                host_login=profile.host_login,
                host_display_name=profile.host_display_name,
            )
        return profile

    def _stream(self, game_hours, profile=None, language="en", status=Stream.Status.APPROVED):
        """A stream seen on each game in `game_hours`, {game: [hours before the newest]}."""
        snapshots = [
            {"g": game.host_game_id, "v": 5, "t": (NEWEST_HOUR - age) * 3600 + 60}
            for game, ages in game_hours.items()
            for age in ages
        ]
        return Stream.objects.create(
            streamer_profile=profile or self._streamer(),
            host_stream_id=self._id(),
            status=status,
            language=language,
            started_at=NOW - timedelta(days=30),
            finished_at=NOW - timedelta(minutes=30),
            snapshots=sorted(snapshots, key=lambda snapshot: snapshot["t"]),
        )

    def _streams(self, game, count, age, **kwargs):
        for _ in range(count):
            self._stream({game: [age]}, **kwargs)

    def _rebuild(self):
        with mock.patch.object(timezone, "now", return_value=NOW):
            call_command("rebuild_game_stats", stdout=StringIO())

    @staticmethod
    def _line(game, language="en", size_group=GameStats.ANY_SIZE):
        """A row's streams by how many hours before the newest they were."""
        row = GameStats.objects.get(game=game, language=language, size_group=size_group)
        return {NEWEST_HOUR - hour: streams for hour, streams in zip(row.hours, row.streams)}

    @staticmethod
    def _order(language="en", size_group=GameStats.ANY_SIZE):
        return list(
            GameStats.objects.filter(language=language, size_group=size_group)
            .order_by("position").values_list("game__host_name", flat=True)
        )


class RebuildGameStatsTests(GameStatsTestCase):
    def test_a_stream_counts_once_in_each_hour_it_was_seen(self):
        game = self._game()
        stream = self._stream({game: [2, 1]})
        # A second poll in the same hour.
        stream.snapshots.append({"g": game.host_game_id, "v": 5, "t": (NEWEST_HOUR - 1) * 3600 + 1260})
        stream.save()
        self._stream({game: [1]})

        self._rebuild()

        self.assertEqual(self._line(game), {1: 2, 2: 1})

    def test_hours_run_newest_first(self):
        game = self._game()
        self._stream({game: [5, 0, 2]})

        self._rebuild()

        row = GameStats.objects.get(game=game, language="en", size_group=GameStats.ANY_SIZE)
        self.assertEqual(row.hours, [NEWEST_HOUR, NEWEST_HOUR - 2, NEWEST_HOUR - 5])

    def test_a_stream_counts_for_each_game_it_played(self):
        first, second = self._game(), self._game()
        self._stream({first: [1], second: [1, 0]})

        self._rebuild()

        self.assertEqual(self._line(first), {1: 1})
        self.assertEqual(self._line(second), {1: 1, 0: 1})

    def test_streams_of_every_status_count(self):
        game = self._game()
        for status in (Stream.Status.LIVE, Stream.Status.OFFLINE, Stream.Status.APPROVED):
            self._stream({game: [0]}, status=status)

        self._rebuild()

        self.assertEqual(self._line(game), {0: 3})

    def test_only_games_count(self):
        non_game = self._game(category=Game.Category.ISNONGAME)
        new = self._game(category=Game.Category.NEW)
        game = self._game()
        self._stream({non_game: [0], new: [0], game: [0]})

        self._rebuild()

        self.assertEqual(set(GameStats.objects.values_list("game_id", flat=True)), {game.id})

    def test_only_the_windows_whole_hours_count(self):
        game = self._game()
        self._stream({game: [-1, 0, WINDOW_HOURS - 1, WINDOW_HOURS]})

        self._rebuild()

        # -1 is the hour in progress; WINDOW_HOURS is the hour just before the window.
        self.assertEqual(self._line(game), {0: 1, WINDOW_HOURS - 1: 1})

    def test_each_size_group_holds_its_own_streamers(self):
        game = self._game()
        self._stream({game: [0]}, profile=self._streamer(peak=10))
        self._stream({game: [0]}, profile=self._streamer(peak=11))
        self._stream({game: [0]}, profile=self._streamer(peak=20))
        self._stream({game: [0]}, profile=self._streamer(peak=201))

        self._rebuild()

        self.assertEqual(self._line(game, size_group=1), {0: 1})
        self.assertEqual(self._line(game, size_group=2), {0: 2})
        self.assertEqual(self._line(game, size_group=5), {0: 1})
        self.assertEqual(self._line(game), {0: 4})

    def test_a_streamers_size_is_the_one_in_the_streams_language(self):
        game = self._game()
        profile = self._streamer(peak=10, language="fr")
        self._stream({game: [0]}, profile=profile, language="fr")
        self._stream({game: [0]}, profile=profile, language="de")

        self._rebuild()

        self.assertEqual(self._line(game, language="fr", size_group=1), {0: 1})
        self.assertFalse(GameStats.objects.filter(language="de", size_group=1).exists())

    def test_a_streamer_with_no_size_counts_under_any_size_only(self):
        game = self._game()
        self._stream({game: [0]})

        self._rebuild()

        self.assertEqual(
            list(GameStats.objects.values_list("language", "size_group").order_by("language")),
            [(ALL_LANGUAGES, GameStats.ANY_SIZE), ("en", GameStats.ANY_SIZE)],
        )

    def test_all_languages_adds_the_languages_up(self):
        game = self._game()
        self._stream({game: [0]}, language="en")
        self._stream({game: [0, 1]}, language="de")

        self._rebuild()

        self.assertEqual(self._line(game, language=ALL_LANGUAGES), {0: 2, 1: 1})

    def test_a_language_the_pages_dont_offer_is_left_out(self):
        game = self._game()
        self._stream({game: [0]}, language="ko")

        self._rebuild()

        self.assertFalse(GameStats.objects.exists())

    def test_a_rebuild_replaces_the_rows(self):
        gone, kept = self._game("gone"), self._game("kept")
        stream = self._stream({gone: [0]})
        self._stream({kept: [0]})
        self._rebuild()

        stream.delete()
        self._rebuild()

        self.assertEqual(self._order(), ["kept"])

    def test_the_newest_hour_is_kept_for_the_search(self):
        self._stream({self._game(): [0]})

        self._rebuild()

        self.assertEqual(GameSearch.newest_hour(), NEWEST_HOUR)


class SortTests(GameStatsTestCase):
    def test_the_newest_hour_decides(self):
        busy_before, on_now = self._game("busy before"), self._game("on now")
        self._streams(busy_before, 5, age=1)
        self._streams(on_now, 1, age=0)

        self._rebuild()

        self.assertEqual(self._order(), ["on now", "busy before"])

    def test_the_most_streams_in_the_newest_hour_comes_first(self):
        few, many = self._game("few"), self._game("many")
        self._streams(few, 1, age=0)
        self._streams(many, 2, age=0)

        self._rebuild()

        self.assertEqual(self._order(), ["many", "few"])

    def test_an_older_hour_breaks_a_tie(self):
        lower, higher = self._game("lower"), self._game("higher")
        for game, before in ((lower, 1), (higher, 3)):
            self._streams(game, 2, age=0)
            self._streams(game, before, age=1)

        self._rebuild()

        self.assertEqual(self._order(), ["higher", "lower"])

    def test_a_tie_can_reach_far_back(self):
        recent, old = self._game("old streams only"), self._game("a later stream")
        self._streams(recent, 1, age=0)
        self._streams(recent, 1, age=500)
        self._streams(old, 1, age=0)
        self._streams(old, 1, age=400)

        self._rebuild()

        self.assertEqual(self._order(), ["a later stream", "old streams only"])

    def test_a_game_with_more_hours_wins_when_the_rest_is_equal(self):
        shorter, longer = self._game("shorter"), self._game("longer")
        self._streams(shorter, 1, age=0)
        self._streams(longer, 1, age=0)
        self._streams(longer, 1, age=3)

        self._rebuild()

        self.assertEqual(self._order(), ["longer", "shorter"])

    def test_each_list_has_its_own_order(self):
        small_game, big_game = self._game("small game"), self._game("big game")
        self._streams(small_game, 3, age=0, profile=self._streamer(peak=15))
        self._streams(big_game, 1, age=0, profile=self._streamer(peak=15))
        self._streams(big_game, 5, age=0, profile=self._streamer(peak=300))

        self._rebuild()

        self.assertEqual(self._order(size_group=2), ["small game", "big game"])
        self.assertEqual(self._order(), ["big game", "small game"])

    def test_positions_count_from_one_in_every_list(self):
        for name in ("one", "two", "three"):
            self._stream({self._game(name): [0]})

        self._rebuild()

        positions = GameStats.objects.filter(language="en", size_group=GameStats.ANY_SIZE).values_list("position", flat=True)
        self.assertEqual(sorted(positions), [1, 2, 3])


class GameSearchTests(GameStatsTestCase):
    def _names(self, **filters):
        return [row["name"] for row in GameSearch(filters).results()]

    def test_results_are_one_lists_order(self):
        first, second = self._game("first"), self._game("second")
        self._streams(first, 2, age=0, language="de")
        self._streams(second, 1, age=0, language="de")
        self._streams(second, 5, age=0, language="fr")
        self._rebuild()

        self.assertEqual(self._names(lang="de"), ["first", "second"])
        self.assertEqual(self._names(lang="fr"), ["second"])
        self.assertEqual(self._names(), ["second", "first"])

    def test_the_size_filter_reads_that_groups_list(self):
        small_game, big_game = self._game("small game"), self._game("big game")
        self._streams(small_game, 1, age=0, profile=self._streamer(peak=15))
        self._streams(big_game, 5, age=0, profile=self._streamer(peak=300))
        self._rebuild()

        self.assertEqual(self._names(lang="en", peak="11-20"), ["small game"])
        self.assertEqual(self._names(lang="en", peak="201+"), ["big game"])
        self.assertEqual(self._names(lang="en", peak="any"), ["big game", "small game"])

    def test_genres_narrow_the_results(self):
        indie, puzzle = self._genre(32, "Indie"), self._genre(9, "Puzzle")
        both = self._game("both", genres=[indie, puzzle])
        one = self._game("one", genres=[indie])
        self._stream({both: [0], one: [0]})
        self._rebuild()

        self.assertEqual(set(self._names(genres=32)), {"both", "one"})
        self.assertEqual(self._names(genres=32, genres2=9), ["both"])
        self.assertEqual(self._names(genres=9, genres3=9), ["both"])

    def test_the_year_filter(self):
        new = self._game("new", release_date=date(2026, 3, 1))
        old = self._game("old", release_date=date(2010, 3, 1))
        undated = self._game("undated")
        self._stream({new: [0], old: [0], undated: [0]})
        self._rebuild()

        self.assertEqual(self._names(year=2026), ["new"])
        self.assertEqual(self._names(year="2010"), ["old"])
        self.assertEqual(len(self._names(year="any")), 3)

    def test_a_year_no_game_has_is_no_filter(self):
        self._stream({self._game("one", release_date=date(2026, 3, 1)): [0]})
        self._rebuild()

        self.assertEqual(self._names(year=1800), ["one"])

    def test_an_unknown_value_falls_back_to_the_default(self):
        self._stream({self._game("one"): [0]}, language="de")
        self._rebuild()

        self.assertEqual(self._names(lang="xx", peak="nonsense", genres="1 OR 1=1"), ["one"])

    def test_a_row_shows_its_newest_hours_with_the_empty_ones_as_zero(self):
        indie, puzzle = self._genre(32, "Indie"), self._genre(9, "Puzzle")
        game = self._game("one", genres=[puzzle, indie], release_date=date(2024, 12, 31))
        self._streams(game, 2, age=0)
        self._streams(game, 1, age=2)
        self._streams(game, 7, age=3)
        self._rebuild()

        self.assertEqual(GameSearch({"lang": "en"}).results(), [{
            "id": game.id,
            "name": "one",
            "release_year": 2024,
            "genres": ["Indie", "Puzzle"],
            "recent_streams": [2, 0, 1],
        }])

    def test_a_game_with_nothing_lately_shows_zeros(self):
        game = self._game("one")
        self._streams(game, 4, age=10)
        self._rebuild()

        self.assertEqual(GameSearch({"lang": "en"}).results()[0]["recent_streams"], [0, 0, 0])

    def test_total_counts_what_the_filters_let_through(self):
        indie = self._genre(32, "Indie")
        self._stream({self._game("one", genres=[indie]): [0], self._game("two"): [0]})
        self._rebuild()

        self.assertEqual(GameSearch({"lang": "en"}).total(), 2)
        self.assertEqual(GameSearch({"lang": "en", "genres": 32}).total(), 1)

    def test_paging(self):
        for number in range(3):
            self._streams(self._game(f"game {number}"), number + 1, age=0)
        self._rebuild()

        self.assertEqual([row["name"] for row in GameSearch({"lang": "en"}).results(offset=1, limit=1)], ["game 1"])

    def test_a_game_with_no_stats_yet_is_no_error(self):
        self.assertEqual(GameSearch().results(), [])
        self.assertIsNone(GameSearch.newest_hour())

    def test_hours_of_a_game(self):
        game = self._game("one")
        self._stream({game: [1, 0]}, profile=self._streamer(peak=15), language="en")
        self._stream({game: [0]}, language="de")
        self._rebuild()

        everyone = GameSearch.hours_of_game(game.id, "any")
        self.assertEqual(everyone["newest_hour"], NEWEST_HOUR)
        self.assertEqual(everyone["window_hours"], WINDOW_HOURS)
        self.assertEqual(everyone["lines"], {
            "en": {"hours": [NEWEST_HOUR, NEWEST_HOUR - 1], "streams": [1, 1]},
            "de": {"hours": [NEWEST_HOUR], "streams": [1]},
        })
        self.assertEqual(set(GameSearch.hours_of_game(game.id, "11-20")["lines"]), {"en"})
        self.assertEqual(GameSearch.hours_of_game(game.id, "201+")["lines"], {})


class GameApiTests(GameStatsTestCase):
    def test_search_endpoint(self):
        game = self._game("one")
        self._streams(game, 2, age=0)
        self._rebuild()

        response = self.client.get("/games/", {"lang": "en", "p": "1"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data["total"], data["newest_hour"]), (1, NEWEST_HOUR))
        self.assertEqual(data["results"][0]["recent_streams"], [2, 0, 0])

    def test_search_is_public_and_pages(self):
        self._stream({self._game("one"): [0]})
        self._rebuild()

        self.assertEqual(self.client.get("/games/", {"p": "2"}).json()["results"], [])
        self.assertEqual(self.client.get("/games/", {"p": "nonsense"}).json()["total"], 1)

    def test_hours_endpoint(self):
        game = self._game("one")
        self._stream({game: [0]}, profile=self._streamer(peak=15))
        self._rebuild()

        response = self.client.get(f"/games/{game.id}/hours/", {"peak": "11-20"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lines"], {"en": {"hours": [NEWEST_HOUR], "streams": [1]}})
