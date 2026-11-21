"""Tests for the Games pages' cached text: a page per language, the form's filters, the guide,
and each language's "What stands out" sentences."""

from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.pages.cached_pages.games import GamesPageBuilder
from apps.streams.game_search import GameSearch
from apps.streams.languages import PAGE_LANGUAGES
from apps.streams.models import Game, GameStats


class GamesPageTests(TestCase):
    def setUp(self):
        GameSearch.get_filters_config.cache_clear()

    @staticmethod
    def _content(year, month, day):
        with mock.patch.object(timezone, "now", return_value=datetime(year, month, day, 9, tzinfo=dt_timezone.utc)):
            return GamesPageBuilder().build_content()

    def test_a_page_per_language(self):
        pages = self._content(2026, 11, 4)["language_pages"]

        self.assertEqual([page["code"] for page in pages], list(PAGE_LANGUAGES))
        self.assertEqual((pages[0]["slug"], pages[0]["title"]), ("english", "Most Streamed Games on Twitch in English"))

    def test_a_language_collected_for_less_than_4_weeks_is_noted(self):
        notes = {page["code"]: page["note"] for page in self._content(2026, 11, 4)["language_pages"]}
        self.assertIn("2 November 2026", notes["ja"])
        self.assertIsNone(notes["en"])
        hours = {page["code"]: page["since_hour"] for page in self._content(2026, 11, 4)["language_pages"]}
        self.assertEqual(hours["ja"] * 3600, datetime(2026, 11, 2, tzinfo=dt_timezone.utc).timestamp())
        self.assertIsNone(hours["en"])

        later = {page["code"]: page["note"] for page in self._content(2026, 11, 30)["language_pages"]}
        self.assertIsNone(later["ja"])

    def test_the_form_offers_the_size_groups(self):
        filters = {one["name"]: one for one in self._content(2026, 11, 4)["search_form"]["filters"]}

        self.assertEqual(
            [value["v"] for value in filters["peak"]["values"]],
            ["any", "3-10", "11-20", "21-50", "51-200", "201+"],
        )
        self.assertNotIn("lang", filters)

    def test_the_form_ends_with_a_name_box(self):
        filters = self._content(2026, 11, 4)["search_form"]["filters"]

        self.assertEqual(filters[-1]["name"], "name")
        self.assertEqual((filters[-1]["type"], filters[-1]["default"], filters[-1]["values"]), ("text", "", []))

    def test_the_guide_and_the_questions(self):
        content = self._content(2026, 11, 4)

        self.assertEqual(len(content["guide"]["steps"]), 4)
        questions = [item["question"] for item in content["faq"]["items"]]
        self.assertIn("Which games are streamed most on Twitch right now?", questions)


class GamesStandoutTests(TestCase):
    """A language page's games against the other languages: its most streamed game, and those
    of its top games that rank far lower elsewhere."""

    def setUp(self):
        GameSearch.get_filters_config.cache_clear()
        self.next_id = 0
        # English streams 20 games, 300 stream-hours for the first down to 110 for the last.
        self.english = [self._game(f"E{place}") for place in range(1, 21)]
        for place, game in enumerate(self.english, 1):
            self._stats(game, "en", 310 - 10 * place)
        # French: the top English game first, then the 20th, a game only French streams, and
        # the 2nd, which ranks about as high in both.
        self._stats(self.english[0], "fr", 50)
        self._stats(self.english[19], "fr", 40)
        self._stats(self._game("Solo"), "fr", 30)
        self._stats(self.english[1], "fr", 20)

    def _game(self, name):
        self.next_id += 1
        return Game.objects.create(host_game_id=self.next_id, host_name=name, category=Game.Category.ISGAME)

    @staticmethod
    def _stats(game, language, total):
        # Two hours with streams, adding up to the total.
        GameStats.objects.create(
            game=game, language=language, size_group=GameStats.ANY_SIZE, position=1,
            hours=[2, 1], streams=[total - 1, 1],
        )

    @staticmethod
    def _standouts(code, year=2026, month=11, day=21):
        with mock.patch.object(timezone, "now", return_value=datetime(year, month, day, 9, tzinfo=dt_timezone.utc)):
            pages = GamesPageBuilder().build_content()["language_pages"]
        return {page["code"]: page["standouts"] for page in pages}[code]

    def test_the_top_game_and_the_games_far_lower_elsewhere(self):
        standouts = self._standouts("fr")

        self.assertEqual(standouts["title"], "What stands out in French")
        games, places = standouts["paragraphs"]
        self.assertIn(
            "Over the last 4 weeks, the most streamed game in French was E1, as it was in the other languages.",
            games,
        )
        # E2 is #4 in French and #2 elsewhere, so it isn't one.
        self.assertIn(
            "Some of the games streamed most in French rank far lower elsewhere: Solo is #3 in French and isn't"
            " streamed elsewhere; E20 is #2 and #20.",
            games,
        )
        self.assertTrue(places.startswith("These places add up the streams live on each game"))

    def test_a_language_with_no_games_far_lower_elsewhere_says_so(self):
        GameStats.objects.filter(language="fr").delete()
        self._stats(self.english[1], "fr", 50)
        self._stats(self.english[0], "fr", 40)

        text = self._standouts("fr")["paragraphs"][0]
        self.assertIn("the most streamed game in French was E2, which is #2 in the other languages.", text)
        self.assertIn("The other games streamed most in French rank about as high in the other languages.", text)

    def test_no_standouts_for_a_language_collected_for_under_a_week(self):
        self._stats(self.english[0], "ja", 50)

        self.assertIsNone(self._standouts("ja", 2026, 11, 5))
        self.assertIsNotNone(self._standouts("ja", 2026, 11, 9))

    def test_no_standouts_for_a_language_with_no_games(self):
        self.assertIsNone(self._standouts("de"))
