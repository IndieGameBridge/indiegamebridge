"""Tests for the precomputed search read-model.

Two layers:
  - rebuild_search_stats turns approved streams into one StreamerSearchStats row
    per (streamer, language) for the last 4 weeks.
  - StreamerSearch filters/sorts that table and shapes the result rows.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.streams.distribution import LANGUAGES
from apps.streams.models import (
    GameGenre,
    SearchStatsRebuildState,
    Stream,
    StreamerProfile,
    StreamerSearchStats,
)
from apps.streams.search import StreamerSearch

# StreamerSearch applies the search form's defaults to every call (peak/avg 5-200,
# >= 4 streams, >= 8 hours), so a bare StreamerSearch() means "the default search",
# not "no filters". The tests below probe one filter at a time against deliberately
# tiny fixtures, so they neutralise the rest explicitly: "any" is the config's
# no-filter sentinel, and streamsmin has no "any" option so it takes its lowest
# value instead. test_default_filters_apply covers the defaults themselves.
NO_FILTERS = {
    "peakmin": "any", "peakmax": "any",
    "avgmin": "any", "avgmax": "any",
    "streamsmin": 1, "streamsmax": "any",
    "hoursmin": "any", "hoursmax": "any",
}


class RebuildAndSearchTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so each test builds them from its own
        # GameGenre rows rather than a prior test's empty snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()

    def _make_streamer(self, host_user_id, login):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _make_stream(self, profile, host_stream_id, max_viewers, avg_viewers,
                     duration, language="en", genre_ids=None, days_ago=1):
        return Stream.objects.create(
            streamer_profile=profile,
            host_stream_id=host_stream_id,
            status=Stream.Status.APPROVED,
            language=language,
            started_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            finished_at=timezone.now() - timedelta(days=days_ago),
            snapshots=[],
            max_viewers=max_viewers,
            avg_viewers=avg_viewers,
            duration=duration,
            genre_ids=genre_ids or [],
        )

    def _rebuild(self):
        # reset so each call processes the whole set regardless of where the
        # rolling cursor left off (keeps tests independent of chunk cadence).
        call_command("rebuild_search_stats", reset=True)

    def _search(self, **overrides):
        """A search with only the filters under test applied (see NO_FILTERS)."""
        return StreamerSearch({**NO_FILTERS, **overrides})

    def _logins(self, results):
        return [row["login"] for row in results]

    def test_aggregates_per_streamer(self):
        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, max_viewers=100, avg_viewers=40, duration=3600, genre_ids=[10, 20])
        self._make_stream(streamer, 2, max_viewers=150, avg_viewers=80, duration=7200, genre_ids=[20, 30])

        self._rebuild()

        stats = StreamerSearchStats.objects.get(streamer_profile=streamer, language="en")
        self.assertEqual(stats.peak_viewers, 150)
        self.assertEqual(stats.avg_viewers, 60)  # mean of 40 and 80
        self.assertEqual(stats.total_duration_seconds, 10800)
        self.assertEqual(stats.streams_count, 2)
        self.assertEqual(stats.genre_ids, [10, 20, 30])  # union, de-duped, sorted

    def test_separate_rows_per_language(self):
        bob = self._make_streamer(1, "bob")
        self._make_stream(bob, 1, max_viewers=10, avg_viewers=5, duration=3600, language="en")
        self._make_stream(bob, 2, max_viewers=20, avg_viewers=15, duration=3600, language="fr")
        self._make_stream(bob, 3, max_viewers=30, avg_viewers=25, duration=3600, language="es")

        self._rebuild()

        en = StreamerSearchStats.objects.get(streamer_profile=bob, language="en")
        fr = StreamerSearchStats.objects.get(streamer_profile=bob, language="fr")
        es = StreamerSearchStats.objects.get(streamer_profile=bob, language="es")
        self.assertEqual((en.peak_viewers, en.avg_viewers), (10, 5))
        self.assertEqual((fr.peak_viewers, fr.avg_viewers), (20, 15))
        self.assertEqual((es.peak_viewers, es.avg_viewers), (30, 25))

    def test_streams_outside_window_are_excluded(self):
        active = self._make_streamer(1, "active")
        dormant = self._make_streamer(2, "dormant")
        self._make_stream(active, 1, max_viewers=50, avg_viewers=20, duration=3600, days_ago=1)
        self._make_stream(dormant, 2, max_viewers=50, avg_viewers=20, duration=3600, days_ago=40)

        self._rebuild()

        self.assertTrue(StreamerSearchStats.objects.filter(streamer_profile=active).exists())
        self.assertFalse(StreamerSearchStats.objects.filter(streamer_profile=dormant).exists())

    def test_rebuild_prunes_now_dormant_rows(self):
        streamer = self._make_streamer(1, "solo")
        recent = self._make_stream(streamer, 1, max_viewers=50, avg_viewers=20, duration=3600, days_ago=1)
        self._rebuild()
        self.assertTrue(StreamerSearchStats.objects.filter(streamer_profile=streamer).exists())

        # Stream ages out of the window; a re-run should drop the stale row.
        recent.finished_at = timezone.now() - timedelta(days=40)
        recent.save(update_fields=["finished_at"])
        self._rebuild()

        self.assertFalse(StreamerSearchStats.objects.filter(streamer_profile=streamer).exists())

    def test_search_peak_filter(self):
        low = self._make_streamer(1, "low")
        high = self._make_streamer(2, "high")
        self._make_stream(low, 1, max_viewers=10, avg_viewers=5, duration=3600)
        self._make_stream(high, 2, max_viewers=150, avg_viewers=5, duration=3600)
        self._rebuild()

        results = self._search(peakmin="100").results()

        self.assertEqual(self._logins(results), ["high"])

    def test_search_streams_count_filter(self):
        rare = self._make_streamer(1, "rare")
        frequent = self._make_streamer(2, "frequent")
        self._make_stream(rare, 1, max_viewers=50, avg_viewers=20, duration=3600)
        for i in range(5):
            self._make_stream(frequent, 10 + i, max_viewers=50, avg_viewers=20, duration=3600)
        self._rebuild()

        results = self._search(streamsmin="3").results()

        self.assertEqual(self._logins(results), ["frequent"])

    def test_search_hours_filter(self):
        short = self._make_streamer(1, "short")
        long = self._make_streamer(2, "long")
        self._make_stream(short, 1, max_viewers=50, avg_viewers=20, duration=3600)  # 1h
        self._make_stream(long, 2, max_viewers=50, avg_viewers=20, duration=36000)  # 10h
        self._rebuild()

        # hoursmin is entered in hours; rows below 5h total are filtered out.
        results = self._search(hoursmin="5").results()

        self.assertEqual(self._logins(results), ["long"])

    def test_search_sort_peak_then_avg_then_duration(self):
        top_peak = self._make_streamer(1, "toppeak")
        avg_hi = self._make_streamer(2, "avghi")
        avg_lo = self._make_streamer(3, "avglo")
        dur_hi = self._make_streamer(4, "durhi")
        self._make_stream(top_peak, 1, max_viewers=200, avg_viewers=5, duration=1)
        self._make_stream(avg_hi, 2, max_viewers=100, avg_viewers=90, duration=10)
        self._make_stream(avg_lo, 3, max_viewers=100, avg_viewers=50, duration=9000)
        self._make_stream(dur_hi, 4, max_viewers=100, avg_viewers=90, duration=8000)
        self._rebuild()

        results = self._search().results()

        self.assertEqual(self._logins(results), ["toppeak", "durhi", "avghi", "avglo"])

    def test_search_genre_overlap(self):
        GameGenre.objects.create(host_genre_id=10, host_name="Action", host_url="", slug="action")
        GameGenre.objects.create(host_genre_id=20, host_name="Puzzle", host_url="", slug="puzzle")
        action = self._make_streamer(1, "action")
        puzzle = self._make_streamer(2, "puzzle")
        self._make_stream(action, 1, max_viewers=50, avg_viewers=20, duration=3600, genre_ids=[10])
        self._make_stream(puzzle, 2, max_viewers=50, avg_viewers=20, duration=3600, genre_ids=[20])
        self._rebuild()

        results = self._search(genres="10").results()

        self.assertEqual(self._logins(results), ["action"])
        self.assertEqual(results[0]["genres"], ["Action"])

    def test_search_language_isolation(self):
        bob = self._make_streamer(1, "bob")
        self._make_stream(bob, 1, max_viewers=10, avg_viewers=5, duration=3600, language="en")
        self._make_stream(bob, 2, max_viewers=20, avg_viewers=15, duration=3600, language="fr")
        self._make_stream(bob, 3, max_viewers=30, avg_viewers=25, duration=3600, language="es")
        self._rebuild()

        en_results = self._search(lang="en").results()
        fr_results = self._search(lang="fr").results()
        es_results = self._search(lang="es").results()

        self.assertEqual(en_results[0]["peak_viewers"], 10)
        self.assertEqual(fr_results[0]["peak_viewers"], 20)
        self.assertEqual(es_results[0]["peak_viewers"], 30)

    def test_result_row_shape(self):
        streamer = self._make_streamer(1, "solo")
        self._make_stream(streamer, 1, max_viewers=100, avg_viewers=40, duration=7200)
        self._rebuild()

        (row,) = self._search().results()

        self.assertEqual(row["login"], "solo")
        self.assertEqual(row["display_name"], "Solo")
        self.assertEqual(row["profile_id"], streamer.id)
        self.assertEqual(row["peak_viewers"], 100)
        self.assertEqual(row["avg_viewers"], 40)
        self.assertEqual(row["hours_streamed"], 2)  # 7200s -> 2h
        self.assertEqual(row["streams_count"], 1)
        self.assertNotIn("total_duration_seconds", row)

    def test_default_filters_apply_when_none_are_given(self):
        # A bare search is the form's default search, not an unfiltered one. Locks
        # the defaults (>= 4 streams, >= 8 hours) that moved once already and left
        # every other search test here asserting an empty result set.
        casual = self._make_streamer(1, "casual")
        regular = self._make_streamer(2, "regular")
        self._make_stream(casual, 1, max_viewers=50, avg_viewers=20, duration=3600)
        for i in range(4):
            self._make_stream(regular, 10 + i, max_viewers=50, avg_viewers=20, duration=3 * 3600)
        self._rebuild()

        self.assertEqual(self._logins(StreamerSearch().results()), ["regular"])

    def test_language_filter_offers_every_tracked_language(self):
        # This dropdown is the only whitelist ?lang= is validated against, so a
        # language surfaced elsewhere but missing here silently falls back to the
        # default one instead of erroring.
        filters_config, _ = StreamerSearch.get_filters_config()
        lang_filter = next(one for one in filters_config if one["name"] == "lang")

        self.assertEqual([one["v"] for one in lang_filter["values"]], LANGUAGES)

    def test_pass_completes_while_new_profiles_keep_arriving(self):
        # Regression: the cursor used to wrap only on a run that found *nothing* past
        # it. fetch_twitch_streams inserts profiles continuously, so that run never
        # came - the cursor pinned itself to the top of the id range and every row
        # below it was never recomputed again (leaving the read-model months stale).
        for host_id in (1, 2):
            streamer = self._make_streamer(host_id, f"s{host_id}")
            self._make_stream(streamer, host_id, max_viewers=50, avg_viewers=20, duration=3600)

        call_command("rebuild_search_stats", reset=True, chunk=2)
        self.assertNotEqual(self._cursor(), 0)  # full chunk -> pass still open

        # A new streamer lands above the cursor, as the fetch cron would create it.
        newcomer = self._make_streamer(3, "s3")
        self._make_stream(newcomer, 3, max_viewers=50, avg_viewers=20, duration=3600)

        call_command("rebuild_search_stats", chunk=2)
        self.assertEqual(self._cursor(), 0)
        self.assertEqual(StreamerSearchStats.objects.count(), 3)

    @staticmethod
    def _cursor():
        state = SearchStatsRebuildState.objects.filter(pk=1).first()
        return state.last_profile_id if state else 0
