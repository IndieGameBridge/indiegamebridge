"""Tests for the per-game public pages, /game/<slug>.

rebuild_game_pages counts each game's last 4 weeks from the approved streams, and gives a page
to every game enough different streamers played. Covered here:

  - which games get a page, and the address each one gets;
  - a page never goes away or moves: a quiet game's drops to zero, a small one to totals;
  - the numbers: streams, hours, languages, weeks and sizes, and the games also played;
  - the baselines the pages compare with;
  - the page's text and sections, from its numbers;
  - the API: a page, a 404 for an address never given out, and the sitemap's list.
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.streams.game_pages import BASELINES_CACHE_KEY, GamePageContent, new_slug
from apps.streams.game_search import GameSearch
from apps.streams.models import (
    Game,
    GameGenre,
    GamePage,
    GameStats,
    JsonCache,
    Stream,
    StreamerProfile,
    StreamerSearchStats,
)

NOW = datetime(2026, 11, 3, 10, 30, tzinfo=dt_timezone.utc)


class GamePagesTestCase(TestCase):
    def setUp(self):
        cache.clear()  # the throttle counters live there
        GameSearch.get_filters_config.cache_clear()
        self.next_id = 0

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _game(self, name, genres=(), year=None, igdb=None, category=Game.Category.ISGAME):
        number = self._id()
        game = Game.objects.create(
            host_game_id=1000 + number,
            igdb_game_id=igdb or number,
            host_name=name,
            category=category,
            release_date=date(year, 1, 1) if year else None,
        )
        game.genres.set(genres)
        return game

    def _streamer(self, peak=None, language="en"):
        number = self._id()
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=number,
            host_login=f"login{number}",
            host_display_name=f"Display{number}",
        )
        if peak is not None:
            StreamerSearchStats.objects.create(
                streamer_profile=profile, language=language, peak_viewers=peak, avg_viewers=5,
                total_duration_seconds=3600, streams_count=1,
                host_login=profile.host_login, host_display_name=profile.host_display_name,
            )
        return profile

    def _stream(self, profile, *games, language="en", days_ago=1, duration=3600, status=Stream.Status.APPROVED):
        finished = NOW - timedelta(days=days_ago)
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=self._id(),
            status=status,
            language=language,
            started_at=finished - timedelta(seconds=duration),
            finished_at=finished,
            snapshots=[],
            duration=duration,
            host_game_ids=[game.host_game_id for game in games],
        )

    def _players(self, game, count, **kwargs):
        """`count` different streamers, each with one stream of the game."""
        return [self._stream(self._streamer(), game, **kwargs).streamer_profile for _ in range(count)]

    def _filler(self, count):
        """Streamers of some other game, so that streamers in general play any one game rarely."""
        game = self._game("Filler")
        start = self._id() * 1000
        profiles = StreamerProfile.objects.bulk_create([
            StreamerProfile(host=StreamerProfile.Host.TWITCH, host_user_id=start + n, host_login=f"filler{n}",
                            host_display_name=f"Filler{n}")
            for n in range(count)
        ])
        Stream.objects.bulk_create([
            Stream(streamer_profile=profile, host_stream_id=start + n, status=Stream.Status.APPROVED, language="en",
                   started_at=NOW - timedelta(days=2), finished_at=NOW - timedelta(days=1), snapshots=[],
                   duration=3600, host_game_ids=[game.host_game_id])
            for n, profile in enumerate(profiles)
        ])

    def _rebuild(self, now=NOW):
        with mock.patch.object(timezone, "now", return_value=now):
            call_command("rebuild_game_pages", stdout=StringIO())

    @staticmethod
    def _page(game):
        return GamePage.objects.get(game=game)


class WhichGamesGetPagesTests(GamePagesTestCase):
    def test_a_game_gets_a_page_at_ten_different_streamers(self):
        nine, ten = self._game("Nine Streamers"), self._game("Ten Streamers")
        self._players(nine, 9)
        self._players(ten, 10)

        self._rebuild()

        self.assertEqual(
            list(GamePage.objects.values_list("game__host_name", "slug", "streamers")),
            [("Ten Streamers", "ten-streamers", 10)],
        )

    def test_one_streamers_streams_count_once(self):
        game = self._game("Solo")
        streamer = self._streamer()
        for _ in range(10):
            self._stream(streamer, game)

        self._rebuild()

        self.assertFalse(GamePage.objects.exists())

    def test_only_approved_streams_of_games_in_the_page_languages_and_the_window_count(self):
        game = self._game("Counted")
        self._players(game, 6)
        self._players(game, 1, status=Stream.Status.OFFLINE)
        self._players(game, 1, language="ru")
        self._players(game, 1, days_ago=29)
        self._players(game, 1, days_ago=27)
        chatting = self._game("Just Chatting", category=Game.Category.ISNONGAME)
        self._players(chatting, 10)

        self._rebuild()

        self.assertFalse(GamePage.objects.exists())

    def test_of_two_games_with_one_name_the_more_streamed_gets_the_plain_address(self):
        remake, original = self._game("Resident Evil 4", year=2023), self._game("Resident Evil 4", year=2005)
        self._players(original, 10)
        self._players(remake, 12)

        self._rebuild()

        self.assertEqual(self._page(remake).slug, "resident-evil-4")
        self.assertEqual(self._page(original).slug, "resident-evil-4-2005")

    def test_a_name_two_pages_share_gets_the_year(self):
        remake, original = self._game("Resident Evil 4", year=2023), self._game("Resident Evil 4", year=2005)
        other = self._game("Other Game", year=2020)
        for game in (remake, original, other):
            self._players(game, 10)

        self._rebuild()

        self.assertEqual(
            sorted(GamePage.objects.values_list("name", flat=True)),
            ["Other Game", "Resident Evil 4 (2005)", "Resident Evil 4 (2023)"],
        )

    def test_an_address_never_changes(self):
        game = self._game("Old Name")
        self._players(game, 10)
        self._rebuild()
        game.host_name = "New Name"
        game.save()

        self._rebuild()

        self.assertEqual(self._page(game).slug, "old-name")

    def test_a_quiet_games_page_stays_at_zero(self):
        game = self._game("Faded")
        self._players(game, 10, days_ago=2)
        self._rebuild()
        last = self._page(game).last_streamed_at

        self._rebuild(now=NOW + timedelta(days=30))

        page = self._page(game)
        self.assertEqual((page.slug, page.streamers, page.numbers, page.last_streamed_at), ("faded", 0, {}, last))

    def test_a_page_below_five_streamers_keeps_totals_only(self):
        game = self._game("Fading")
        self._players(game, 10, days_ago=20)
        self._players(game, 3, days_ago=1)
        self._rebuild()
        self.assertIn("languages", self._page(game).numbers)

        # Ten days on, the first ten streamers' streams are out of the window.
        self._rebuild(now=NOW + timedelta(days=10))

        page = self._page(game)
        self.assertEqual(page.streamers, 3)
        self.assertEqual(page.numbers, {"streams": 3, "hours": 3})


class SlugTests(SimpleTestCase):
    def test_the_address_is_the_name(self):
        self.assertEqual(new_slug("Hollow Knight: Silksong", 2025, 1, set()), "hollow-knight-silksong")
        self.assertEqual(new_slug("Pokémon Go", 2016, 1, set()), "pokemon-go")
        self.assertEqual(new_slug("R.E.P.O.", 2025, 1, set()), "repo")

    def test_a_name_taken_adds_the_year_then_the_id(self):
        self.assertEqual(new_slug("Monopoly", 1995, 7, {"monopoly"}), "monopoly-1995")
        self.assertEqual(new_slug("Monopoly", 1995, 7, {"monopoly", "monopoly-1995"}), "monopoly-7")
        self.assertEqual(new_slug("Monopoly", None, 7, {"monopoly"}), "monopoly-7")

    def test_a_name_with_no_latin_letters_takes_the_id(self):
        self.assertEqual(new_slug("原神", 2020, 513181, set()), "513181")

    def test_an_address_is_never_given_twice(self):
        self.assertEqual(new_slug("原神", 2020, 513181, {"513181"}), "513181-2")


class NumbersTests(GamePagesTestCase):
    def test_streams_hours_languages_and_weeks(self):
        game, other = self._game("Counted"), self._game("Other")
        english = [self._streamer() for _ in range(8)]
        for profile in english:
            self._stream(profile, game, duration=7200, days_ago=1)
        # Two hours of two games: one hour each.
        self._stream(english[0], game, other, duration=7200, days_ago=10)
        self._players(game, 1, language="fr", days_ago=15)
        self._players(game, 1, language="de", days_ago=22)

        self._rebuild()

        numbers = self._page(game).numbers
        self.assertEqual(numbers["streams"], 11)
        self.assertEqual(numbers["hours"], 8 * 2 + 1 + 1 + 1)
        self.assertEqual(numbers["languages"], {
            "en": {"streams": 9, "streamers": 8},
            "fr": {"streams": 1, "streamers": 1},
            "de": {"streams": 1, "streamers": 1},
        })
        # Different streamers in each week, the newest first: one of them played in two.
        self.assertEqual(numbers["weeks"], [8, 1, 1, 1])

    def test_sizes_come_from_the_search_table(self):
        game = self._game("Sized")
        for peak in (5, 5, 5, 5, 5, 15, 30, 100, 300):
            self._stream(self._streamer(peak=peak), game)
        # No size yet: left out.
        self._stream(self._streamer(), game)

        self._rebuild()

        self.assertEqual(self._page(game).numbers["sizes"], [5, 1, 1, 1, 1])

    def test_the_hours_of_the_day_come_from_the_game_stats(self):
        game = self._game("Timed")
        self._players(game, 10)
        hour = int(NOW.timestamp()) // 3600 - 1  # 09:00 UTC
        GameStats.objects.create(game=game, language="all", size_group=GameStats.ANY_SIZE, position=1,
                                 hours=[hour, hour - 1, hour - 25], streams=[4, 2, 1])

        self._rebuild()

        hours_of_day = self._page(game).numbers["hours_of_day"]
        self.assertEqual((hours_of_day[9], hours_of_day[8], sum(hours_of_day)), (4, 3, 7))

    def test_also_played_needs_five_shared_streamers_and_three_times_as_often(self):
        alpha, beta, delta = self._game("Alpha"), self._game("Beta"), self._game("Delta")
        players = self._players(alpha, 10)
        for profile in players[:5]:
            self._stream(profile, beta)
        self._players(beta, 5)
        for profile in players[5:9]:
            self._stream(profile, delta)
        self._players(delta, 6)
        self._filler(100)

        self._rebuild()

        also = self._page(alpha).numbers["also_played"]
        self.assertEqual([(game["name"], game["slug"], game["streamers"]) for game in also], [("Beta", "beta", 5)])
        # (5 of its 10) against (Beta's 10 of all 121 streamers: 10 + 5 + 6 + 100).
        self.assertEqual(also[0]["lift"], round((5 / 10) / (10 / 121), 1))

    def test_also_played_leaves_out_another_category_of_the_same_game(self):
        alpha = self._game("Alpha", igdb=77)
        same_igdb = self._game("Alpha Remastered", igdb=77)
        same_letters = self._game("ALPHA!")
        players = self._players(alpha, 10)
        for other in (same_igdb, same_letters):
            for profile in players[:5]:
                self._stream(profile, other)
            self._players(other, 5)
        self._filler(100)

        self._rebuild()

        self.assertEqual(self._page(alpha).numbers["also_played"], [])

    def test_the_baselines(self):
        indie = GameGenre.objects.create(host_genre_id=32, host_name="Indie", host_url="", slug="indie")
        small, big = self._game("Small", genres=[indie]), self._game("Big")
        self._stream(self._streamer(peak=5), small)
        self._stream(self._streamer(peak=300, language="fr"), big, language="fr")

        self._rebuild()

        baselines = JsonCache.objects.get(key=BASELINES_CACHE_KEY).content
        self.assertEqual(baselines["indie"], {"languages": {"en": 1, "fr": 0}, "sizes": [1, 0, 0, 0, 0]})
        self.assertEqual(baselines["all"], {"languages": {"en": 1, "fr": 1}, "sizes": [1, 0, 0, 0, 1]})


BASELINES = {
    "indie": {"languages": {"en": 70, "fr": 9, "es": 12, "de": 9}, "sizes": [64, 17, 12, 5, 2]},
    "all": {"languages": {"en": 69, "fr": 8, "es": 13, "de": 10}, "sizes": [78, 10, 7, 4, 1]},
}

# Busiest 19:00 to 22:00, quietest 09:00 to 12:00.
HOURS_OF_DAY = [0 if hour in (9, 10, 11) else 50 if hour in (19, 20, 21) else 10 for hour in range(24)]

NUMBERS = {
    "streams": 7180,
    "hours": 19600,
    "languages": {
        "en": {"streams": 63, "streamers": 60},
        "es": {"streams": 21, "streamers": 20},
        "fr": {"streams": 10, "streamers": 10},
        "de": {"streams": 6, "streamers": 6},
    },
    "sizes": [61, 18, 13, 6, 2],
    "weeks": [967, 1078, 1118, 1167],
    "hours_of_day": HOURS_OF_DAY,
    "also_played": [
        {"slug": "hollow-knight", "name": "Hollow Knight", "streamers": 267, "lift": 33.3},
        {"slug": "constance", "name": "Constance", "streamers": 7, "lift": 94.0},
    ],
}


def content(streamers=100, numbers=NUMBERS, genres=("Indie",), name="", last=None, **changes):
    game = Game(host_game_id=511, host_name="Alpha", release_date=date(2025, 3, 1))
    page = GamePage(game=game, slug="alpha", name=name, streamers=streamers, numbers={**numbers, **changes},
                    last_streamed_at=last)
    return GamePageContent(page, BASELINES, list(genres)).payload()


class PageContentTests(SimpleTestCase):
    def test_a_page_says_what_its_numbers_say(self):
        self.assertEqual(content()["summary"]["paragraphs"], [
            "100 streamers played Alpha on Twitch in the last 4 weeks, in 7,180 streams and about 19,600 hours of play.",
            "Interest is easing: 967 streamers played it in the last week, against 1,167 three weeks earlier. Its"
            " streamers' sizes are typical for an indie game: 61% of them peak at 10 viewers or fewer, against 64% for"
            " indie games overall.",
            "It's streamed in Spanish more than indie games usually are: 21% of its streams, against 12%. It's streamed"
            " most between 19:00 and 22:00 UTC, and least between 09:00 and 12:00 UTC. Streamers who played it also"
            " often played Hollow Knight and Constance.",
        ])

    def test_the_sections(self):
        page = content()

        self.assertEqual(page["title"], "Alpha on Twitch")
        self.assertEqual(page["info"], "Indie · released 2025")
        self.assertEqual([tile["value"] for tile in page["tiles"]], ["100", "7,180", "19,600", "4"])
        self.assertEqual(
            [(bar["label"], bar["value"], bar["baseline"]) for bar in page["sizes"]["bars"]],
            [("3-10", "61%", 0.64), ("11-20", "18%", 0.17), ("21-50", "13%", 0.12), ("51-200", "6%", 0.05),
             ("201+", "2%", 0.02)],
        )
        self.assertEqual([bar["label"] for bar in page["languages"]["bars"]], ["English", "Spanish", "French", "German"])
        self.assertEqual(
            [(bar["label"], bar["value"]) for bar in page["weeks"]["bars"]],
            [("4 weeks ago", "1,167"), ("3 weeks ago", "1,118"), ("2 weeks ago", "1,078"), ("Last week", "967")],
        )
        self.assertEqual(
            [(game["href"], game["detail"]) for game in page["also_played"]["games"]],
            [("/game/hollow-knight", "267 streamers, 33× as often"), ("/game/constance", "7, 94×")],
        )

    def test_more_languages_than_the_bars_name_add_up(self):
        languages = {code: {"streams": streams, "streamers": 1} for code, streams in
                     (("en", 50), ("es", 20), ("fr", 10), ("de", 8), ("pt", 6), ("it", 4), ("ja", 2))}

        bars = content(languages=languages)["languages"]["bars"]

        self.assertEqual([(bar["label"], bar["value"]) for bar in bars][-1], ("3 others", "12%"))
        self.assertEqual(len(bars), 5)

    def test_the_trend_in_words(self):
        for newest, word in ((70, "fading"), (80, "easing"), (100, "steady"), (120, "rising"), (130, "growing fast")):
            with self.subTest(word=word):
                paragraph = content(weeks=[newest, 100, 100, 100])["summary"]["paragraphs"][1]
                self.assertTrue(paragraph.startswith(f"Interest is {word}: {newest} streamers played it in the last week"))

    def test_few_streamers_a_week_get_an_average(self):
        paragraph = content(weeks=[6, 5, 4, 2])["summary"]["paragraphs"][1]

        self.assertTrue(paragraph.startswith("About 4 streamers a week played it."))

    def test_sizes_far_from_the_baseline(self):
        small = content(sizes=[80, 10, 5, 4, 1])["summary"]["paragraphs"][1]
        big = content(sizes=[40, 30, 20, 8, 2])["summary"]["paragraphs"][1]

        self.assertIn("It's a small streamers' game: 80% of its streamers peak at 10 viewers or fewer, against 64% for"
                      " indie games.", small)
        self.assertIn("It draws bigger channels than most indie games: 40% of its streamers peak at 10 viewers or"
                      " fewer, against 64%.", big)

    def test_a_language_with_half_its_streams_is_its_favourite(self):
        languages = {"fr": {"streams": 55, "streamers": 5}, "en": {"streams": 45, "streamers": 5}}

        paragraph = content(languages=languages)["summary"]["paragraphs"][2]

        self.assertTrue(paragraph.startswith(
            "It's a French favourite: 55% of its streams are in French, against 9% for indie games."
        ))

    def test_the_busiest_hours_can_run_past_midnight(self):
        hours_of_day = [50 if hour in (23, 0, 1) else 10 for hour in range(24)]

        paragraph = content(hours_of_day=hours_of_day)["summary"]["paragraphs"][2]

        self.assertIn("It's streamed most between 23:00 and 02:00 UTC", paragraph)

    def test_a_game_outside_indie_is_compared_with_every_game(self):
        page = content(genres=("Shooter",))
        typical = content(genres=("Shooter",), sizes=[75, 12, 8, 4, 1])

        # 61% small streamers is 17 points under every game's 78%.
        self.assertIn("It draws bigger channels than most games on Twitch: 61% of its streamers peak at 10 viewers or"
                      " fewer, against 78%.", page["summary"]["paragraphs"][1])
        self.assertIn("typical for a game on Twitch: 75% of them peak at 10 viewers or fewer, against 78% for games on"
                      " Twitch overall.", typical["summary"]["paragraphs"][1])
        self.assertEqual(page["sizes"]["bars"][0]["baseline"], 0.78)

    def test_a_page_shows_its_stored_name(self):
        page = content(name="Alpha (2025)")

        self.assertEqual(page["title"], "Alpha (2025) on Twitch")
        self.assertTrue(page["summary"]["paragraphs"][0].startswith("100 streamers played Alpha (2025) on Twitch"))

    def test_few_streamers_get_totals_only(self):
        page = content(streamers=3, numbers={"streams": 4, "hours": 6})

        self.assertEqual(page["summary"]["paragraphs"], [
            "3 streamers played Alpha on Twitch in the last 4 weeks, in 4 streams and about 6 hours of play. Too few"
            " streamers played it lately to say more."
        ])
        self.assertEqual([tile["label"] for tile in page["tiles"]], ["Streamers", "Streams", "Hours played"])
        for section in ("sizes", "languages", "hours_of_day", "weeks", "also_played", "cta"):
            self.assertIsNone(page[section])

    def test_a_quiet_page_says_when_it_was_last_streamed(self):
        page = content(streamers=0, numbers={}, last=datetime(2026, 10, 2, 20, tzinfo=dt_timezone.utc))

        self.assertEqual(page["summary"]["paragraphs"], [
            "Nobody streamed Alpha on Twitch in the last 4 weeks. It was last streamed on 2 October 2026."
        ])
        self.assertEqual(page["seo_description"], page["summary"]["paragraphs"][0])
        self.assertEqual(page["tiles"], [])

    def test_the_search_links_turn_the_other_filters_off(self):
        cta = content()["cta"]

        self.assertEqual(cta["title"], "The 100 streamers who played it")
        self.assertEqual(cta["login_href"], "/login?next=%2Fgame%2Falpha")
        self.assertEqual(
            [(link["label"], link["streamers"]) for link in cta["search_links"]],
            [("English", "60"), ("Spanish", "20"), ("French", "10"), ("German", "6")],
        )
        self.assertEqual(
            cta["search_links"][0]["href"], "/streamers?game=511&lang=en&peak=any&streamsmin=1&hoursmin=any",
        )


class GamePageApiTests(GamePagesTestCase):
    def _page_of(self, name, slug, streamers, numbers=None):
        return GamePage.objects.create(game=self._game(name), slug=slug, streamers=streamers, numbers=numbers or {})

    def test_a_page_answers_with_its_content(self):
        self._page_of("Alpha", "alpha", 5, {"streams": 9, "hours": 12})

        response = self.client.get("/games/pages/alpha/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Alpha on Twitch")
        self.assertIn("footer_content", data)

    def test_an_address_never_given_out_is_a_404(self):
        self.assertEqual(self.client.get("/games/pages/no-such-game/").status_code, 404)

    def test_a_quiet_page_still_answers(self):
        self._page_of("Faded", "faded", 0)

        response = self.client.get("/games/pages/faded/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["summary"]["paragraphs"], ["Nobody streamed Faded on Twitch in the last 4 weeks."],
        )

    def test_the_sitemaps_list_has_every_page_most_streamed_first(self):
        self._page_of("Few", "few", 3)
        self._page_of("Most", "most", 50)
        self._page_of("Faded", "faded", 0)
        self._page_of("Some", "some", 10)

        self.assertEqual(
            [page["slug"] for page in self.client.get("/games/pages/").json()["pages"]],
            ["most", "some", "few", "faded"],
        )

    def test_a_games_list_row_links_its_page(self):
        page = self._page_of("Alpha", "alpha", 10)
        hour = int(NOW.timestamp()) // 3600
        GameStats.objects.create(game=page.game, language="all", size_group=GameStats.ANY_SIZE, position=1,
                                 hours=[hour], streams=[3])
        without = self._game("Beta")
        GameStats.objects.create(game=without, language="all", size_group=GameStats.ANY_SIZE, position=2,
                                 hours=[hour], streams=[1])

        rows = GameSearch({}).results()

        self.assertEqual([(row["name"], row["slug"]) for row in rows], [("Alpha", "alpha"), ("Beta", None)])

    def test_the_search_names_the_game_its_narrowed_to(self):
        page = self._page_of("Alpha", "alpha", 10)

        data = self.client.get("/streamers/", {"game": page.game.host_game_id}).json()

        self.assertEqual(data["game"], {"id": page.game.host_game_id, "name": "Alpha", "slug": "alpha"})
        self.assertIsNone(self.client.get("/streamers/").json()["game"])
