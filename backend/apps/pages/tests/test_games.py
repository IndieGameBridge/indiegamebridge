"""Tests for the Games pages' cached text: a page per language, and the form's filters."""

from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.pages.cached_pages.games import GamesPageBuilder
from apps.streams.game_search import GameSearch
from apps.streams.languages import PAGE_LANGUAGES


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
        self.assertEqual((pages[0]["slug"], pages[0]["title"]), ("english", "Games in English"))

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
