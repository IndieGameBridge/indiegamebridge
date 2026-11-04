"""Tests for the one-shot backfill of Game.release_date from IGDB."""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.streams.models import Game
from core.utils.igdb_api_client import release_date_of


def _run(response):
    patcher = mock.patch("apps.fetch.management.commands.backfill_game_release_dates.IgdbApiClient")
    client = patcher.start().return_value
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.get_games_by_ids.return_value = response
    try:
        call_command("backfill_game_release_dates", stdout=StringIO())
    finally:
        patcher.stop()
    return client


class BackfillGameReleaseDatesTests(TestCase):
    def _game(self, host_game_id, igdb_game_id=0, category=Game.Category.ISGAME, release_date=None):
        return Game.objects.create(
            host_game_id=host_game_id, igdb_game_id=igdb_game_id, category=category, release_date=release_date,
        )

    def test_fills_the_date_and_skips_a_game_igdb_has_none_for(self):
        dated = self._game(1, igdb_game_id=100)
        undated = self._game(2, igdb_game_id=200)

        _run([{"id": 100, "first_release_date": 1767225600}, {"id": 200}])

        dated.refresh_from_db()
        undated.refresh_from_db()
        self.assertEqual(dated.release_date, date(2026, 1, 1))
        self.assertIsNone(undated.release_date)

    def test_asks_only_about_games_with_an_igdb_id_and_no_date(self):
        self._game(1, igdb_game_id=100)
        self._game(2, igdb_game_id=0)
        self._game(3, igdb_game_id=300, release_date=date(2020, 1, 1))
        self._game(4, igdb_game_id=400, category=Game.Category.ISNONGAME)

        client = _run([])

        self.assertEqual(client.get_games_by_ids.call_args.args[0], [100])


class ReleaseDateOfTests(SimpleTestCase):
    def test_a_timestamp_becomes_a_date(self):
        self.assertEqual(release_date_of({"first_release_date": 1767225600}), date(2026, 1, 1))

    def test_a_date_before_1970(self):
        self.assertEqual(release_date_of({"first_release_date": -86400}), date(1969, 12, 31))

    def test_no_date(self):
        self.assertIsNone(release_date_of({}))
