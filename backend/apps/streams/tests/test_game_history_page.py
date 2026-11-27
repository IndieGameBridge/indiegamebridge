"""Tests for the game pages' month by month section: GameHistoryContent, from GameMonthStats."""

from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.streams.game_pages import GameHistoryContent
from apps.streams.models import ArchivedMonth, Game, GameMonthStats

MONTHS = [date(2026, month, 1) for month in range(5, 11)]  # May to October 2026


class GameHistoryContentTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(host_game_id=33, host_name="Tower", category=Game.Category.ISGAME)
        for index, month in enumerate(MONTHS):
            ArchivedMonth.objects.create(
                month=month, file_name=f"{month:%Y-%m}.parquet", streams_count=1, first_stream_id=index + 1,
                last_stream_id=index + 1, file_size=1, sha256="0" * 64, stats_computed_at=timezone.now(),
            )

    def _row(self, month, streamers, language="all", streams=None, hours=None, viewers=10):
        """A month's numbers: by default a stream and 2 hours per streamer, watched by `viewers`."""
        streams = streamers if streams is None else streams
        hours = 2 * streamers if hours is None else hours
        GameMonthStats.objects.create(
            game=self.game, month=month, language=language, streamers=streamers, streams=streams,
            seconds=hours * 3600, viewer_seconds=viewers * hours * 3600, snapshot_seconds=hours * 3600,
        )

    def _history(self):
        return GameHistoryContent(self.game, "Tower").payload()

    def _rows(self, table):
        return [[row["month"], *row["cells"]] for row in table["rows"]]

    def test_nothing_until_a_counted_month_has_it(self):
        self.assertIsNone(self._history())
        ArchivedMonth.objects.update(stats_computed_at=None)
        self._row(MONTHS[0], 10)
        self.assertIsNone(self._history())

    def test_months_run_from_its_first_one_newest_first_with_the_quiet_ones(self):
        self._row(MONTHS[1], 10)
        self._row(MONTHS[1], 10, "en")
        self._row(MONTHS[3], 6)
        self._row(MONTHS[3], 6, "en")

        history = self._history()

        self.assertEqual(self._rows(history["table"]), [
            ["Oct 2026", "0", "0", "0", "0", "0", "None"],
            ["Sep 2026", "0", "0", "0", "0", "0", "None"],
            ["Aug 2026", "6", "6", "12", "120", "10", "English 100%"],
            ["Jul 2026", "0", "0", "0", "0", "0", "None"],
            ["Jun 2026", "10", "10", "20", "200", "10", "English 100%"],
        ])
        self.assertEqual([bar["value"] for bar in history["bars"]["bars"]], ["0", "0", "6", "0", "10"])
        self.assertIn("since June 2026", history["caption"])

    def test_a_month_under_5_streamers_shows_its_totals_only(self):
        self._row(MONTHS[0], 3)
        self._row(MONTHS[0], 3, "en")

        row = self._history()["table"]["rows"][-1]

        self.assertEqual(row["cells"], ["3", "3", "6", "–", "–", "–"])
        # May is where counting began, on the 4th.
        self.assertEqual(row["month"], "4–31 May 2026")

    def test_main_languages_are_the_two_with_the_most_streams(self):
        self._row(MONTHS[0], 30, streams=100)
        self._row(MONTHS[0], 20, "en", streams=55)
        self._row(MONTHS[0], 8, "fr", streams=40)
        self._row(MONTHS[0], 2, "de", streams=5)

        self.assertEqual(self._history()["table"]["rows"][-1]["cells"][-1], "English 55% · French 40%")

    def test_a_table_for_each_language_with_5_streamers_in_some_month(self):
        self._row(MONTHS[0], 60, streams=60)
        self._row(MONTHS[0], 50, "en")
        self._row(MONTHS[0], 6, "fr")
        self._row(MONTHS[0], 3, "de")
        self._row(MONTHS[1], 4)
        self._row(MONTHS[1], 4, "fr")

        by_language = self._history()["by_language"]

        self.assertEqual([table["heading"] for table in by_language["tables"]], ["Tower on Twitch in English", "Tower on Twitch in French"])
        self.assertEqual(by_language["others"], "Also streamed in German, by fewer than 5 streamers in every month.")
        french = by_language["tables"][1]
        self.assertEqual(self._rows(french["table"])[-5:], [
            ["Sep 2026", "0", "0", "0%", "0", "0", "0"],
            ["Aug 2026", "0", "0", "0%", "0", "0", "0"],
            ["Jul 2026", "0", "0", "0%", "0", "0", "0"],
            ["Jun 2026", "4", "4", "100%", "8", "–", "–"],
            ["4–31 May 2026", "6", "6", "10%", "12", "120", "10"],
        ])
        self.assertEqual(french["text"], "Its busiest month in French was May 2026, with 6 streamers. Nobody streamed it in French after June 2026.")

    def test_a_language_counted_later_starts_from_its_month(self):
        self._row(MONTHS[0], 40)
        self._row(MONTHS[0], 40, "en")
        self._row(MONTHS[3], 50)
        self._row(MONTHS[3], 40, "en")
        self._row(MONTHS[3], 10, "es")

        spanish = self._history()["by_language"]["tables"][1]

        self.assertEqual([row["month"] for row in spanish["table"]["rows"]], ["Oct 2026", "Sep 2026", "16–31 Aug 2026"])
        self.assertTrue(spanish["text"].startswith("Counted from 16 August 2026. Its busiest month in Spanish was August 2026"))

    def test_a_launch_and_its_fall_off(self):
        self.game.release_date = date(2026, 5, 14)
        self.game.save()
        for month, streamers in zip(MONTHS, [1000, 400, 200, 150, 120, 100]):
            self._row(month, streamers)

        text = self._history()["text"]

        self.assertIn("Its busiest month was May 2026, the month it came out: 1,000 streamers played it, and viewers"
                      " watched about 20,000 hours.", text)
        self.assertIn("In October 2026, 100 streamers played it, 10% as many as in May 2026.", text)

    def test_the_months_before_its_release(self):
        self.game.release_date = date(2026, 8, 6)
        self.game.save()
        for month, streamers in zip(MONTHS, [27, 37, 16, 412, 233, 163]):
            self._row(month, streamers)

        self.assertIn("Before then, 16 to 37 streamers a month played it.", self._history()["text"])

    def test_a_game_gone_quiet(self):
        for month, streamers in zip(MONTHS[1:], [338, 3, 0, 0, 1]):
            self._row(month, streamers)

        text = self._history()["text"]

        self.assertTrue(text.startswith("Its busiest month was June 2026: 338 streamers played it"))
        self.assertIn("In the months after, at most 3 streamers a month played it.", text)

    def test_a_steady_game(self):
        for month, streamers in zip(MONTHS, [2598, 2621, 2480, 3044, 3231, 2750]):
            self._row(month, streamers)

        self.assertIn("Between 2,480 and 3,231 streamers played it every month.", self._history()["text"])

    def test_a_busiest_month_that_jumped(self):
        for month, streamers in zip(MONTHS, [8, 17, 85, 30406, 6514, 34960]):
            self._row(month, streamers)

        self.assertIn("Its busiest month was October 2026: 34,960 streamers played it, up from 6,514 in September 2026,",
                      self._history()["text"])

    def test_a_language_that_took_the_lead(self):
        for month, english, french in zip(MONTHS, [17, 25, 10, 455, 248, 149], [12, 12, 10, 349, 264, 182]):
            self._row(month, 40, streams=english + french)
            self._row(month, 20, "en", streams=english)
            self._row(month, 20, "fr", streams=french)

        self.assertIn("Since September 2026, more of its streams have been in French than in English.", self._history()["text"])

    def test_a_language_whose_streams_drew_more_viewers(self):
        self._row(MONTHS[0], 160)
        self._row(MONTHS[0], 83, "en", viewers=15)
        self._row(MONTHS[0], 76, "fr", viewers=89)

        self.assertIn("In May 2026, its French streams averaged 89 viewers, against 15 in English.", self._history()["text"])

    def test_the_notes_say_when_each_language_was_first_counted(self):
        self._row(MONTHS[0], 10)

        self.assertEqual(self._history()["notes"][0], (
            "Counted from 4 May 2026 in English, French and German; from 16 August 2026 in Spanish; and from"
            " 2 November 2026 in Portuguese, Japanese, Italian and Chinese."
        ))
