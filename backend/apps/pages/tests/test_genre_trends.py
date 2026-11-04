"""Tests for the Genre Trends pages' content: a value per language on every genre's bar,
a page of its own for each language, and the notes on languages collected for less than
the 4-week window."""

from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.pages.cached_pages.genre_trends import GenreTrendsPageBuilder
from apps.streams.languages import PAGE_LANGUAGES
from apps.streams.models import GameGenre, GenreStats

COMPUTED_AT = datetime(2026, 11, 3, 7, 12, tzinfo=dt_timezone.utc)


class GenreTrendsPageTests(TestCase):
    def setUp(self):
        shooter = self._genre(5, "Shooter")
        self._genre(9, "Puzzle")
        self._stats(shooter, "en", streams=10, streamers=4, seconds=7200)
        self._stats(shooter, "ja", streams=3, streamers=2, seconds=3600)

    @staticmethod
    def _genre(host_genre_id, name):
        return GameGenre.objects.create(host_genre_id=host_genre_id, host_name=name, host_url="", slug=name.lower())

    @staticmethod
    def _stats(genre, language, streams, streamers, seconds):
        return GenreStats.objects.create(
            genre=genre,
            language=language,
            streams_count=streams,
            streamers_count=streamers,
            total_duration_seconds=seconds,
            computed_at=COMPUTED_AT,
        )

    @staticmethod
    def _content(today):
        now = datetime(today.year, today.month, today.day, 9, tzinfo=dt_timezone.utc)
        with mock.patch.object(timezone, "now", return_value=now):
            return GenreTrendsPageBuilder().build_content()

    def test_every_genre_carries_a_value_per_page_language(self):
        streams, _, hours = self._content(date(2026, 11, 3))["diagrams"]

        self.assertEqual([lang["code"] for lang in streams["languages"]], list(PAGE_LANGUAGES))
        # Zero-value genres stay, after the active ones.
        self.assertEqual([bar["x"] for bar in streams["bars"]], ["Shooter", "Puzzle"])
        self.assertEqual(
            streams["bars"][0]["values"],
            {code: {"en": 10, "ja": 3}.get(code, 0) for code in PAGE_LANGUAGES},
        )
        self.assertEqual((hours["bars"][0]["values"]["en"], hours["bars"][0]["values"]["ja"]), (2, 1))

    def test_each_language_has_a_page_of_its_own(self):
        pages = self._content(date(2026, 11, 3))["language_pages"]

        self.assertEqual([page["code"] for page in pages], list(PAGE_LANGUAGES))
        japanese = pages[PAGE_LANGUAGES.index("ja")]
        self.assertEqual(japanese["slug"], "japanese")
        self.assertEqual(japanese["seo_title"], "Twitch Game Genre Trends in Japanese | IndieGameBridge")

    def test_a_language_collected_for_less_than_4_weeks_says_so(self):
        content = self._content(date(2026, 11, 3))
        notes = {page["code"]: page["note"] for page in content["language_pages"]}

        self.assertEqual(
            notes["ja"],
            "Japanese streams have been collected since 2 November 2026, so these numbers cover 1 day so far,"
            " not 4 weeks.",
        )
        self.assertIsNone(notes["en"])
        self.assertEqual(
            content["note"],
            "Portuguese, Japanese, Italian and Chinese streams have been collected since 2 November 2026, so"
            " their part of these numbers covers 1 day so far, not 4 weeks.",
        )

    def test_the_notes_go_once_the_4_weeks_have_filled(self):
        self.assertIn("27 days", self._content(date(2026, 11, 29))["note"])

        content = self._content(date(2026, 11, 30))
        self.assertIsNone(content["note"])
        self.assertTrue(all(page["note"] is None for page in content["language_pages"]))

    def test_the_data_use_notice_grants_no_license(self):
        self.assertIn("no license is given", self._content(date(2026, 11, 3))["data_use"])

    def test_the_window_ends_when_the_stats_were_computed(self):
        self.assertEqual(
            self._content(date(2026, 11, 3))["window"],
            {"start": "2026-10-06", "end": "2026-11-03", "computed_at": COMPUTED_AT.isoformat()},
        )

    def test_no_window_before_the_stats_are_first_built(self):
        GenreStats.objects.all().delete()

        self.assertIsNone(self._content(date(2026, 11, 3))["window"])
