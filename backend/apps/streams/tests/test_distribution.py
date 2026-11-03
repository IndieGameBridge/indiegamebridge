"""Tests for the home page's peak-viewer distribution: a row per page language, in page
order and named, each streamer in their peak's bucket, and a note while a language's
4 weeks fill."""

from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.streams.distribution import StreamersDistribution
from apps.streams.languages import PAGE_LANGUAGES
from apps.streams.models import StreamerProfile, StreamerSearchStats


class DistributionPayloadTests(TestCase):
    def _search_row(self, host_user_id, language, peak_viewers):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"login{host_user_id}",
            host_display_name=f"Display{host_user_id}",
        )
        return StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language=language,
            peak_viewers=peak_viewers,
            avg_viewers=3,
            total_duration_seconds=3600,
            streams_count=1,
            host_login=profile.host_login,
            host_display_name=profile.host_display_name,
        )

    @staticmethod
    def _payload(today):
        now = datetime(today.year, today.month, today.day, 9, tzinfo=dt_timezone.utc)
        with mock.patch.object(timezone, "now", return_value=now):
            return StreamersDistribution.compute_payload()

    def test_a_row_per_page_language_in_page_order(self):
        payload = self._payload(date(2026, 11, 3))

        self.assertEqual([lang["code"] for lang in payload["languages"]], list(PAGE_LANGUAGES))
        self.assertEqual(payload["languages"][0]["label"], "English")
        self.assertEqual(set(payload["buckets"]), set(PAGE_LANGUAGES))

    def test_a_streamer_counts_in_their_languages_bucket(self):
        self._search_row(1, "ja", peak_viewers=4)
        self._search_row(2, "en", peak_viewers=250)

        buckets = self._payload(date(2026, 11, 3))["buckets"]
        self.assertEqual(buckets["ja"][0], {"x": "3-5", "y": 1})
        self.assertEqual(buckets["en"][-1], {"x": "201+", "y": 1})
        self.assertEqual(sum(bucket["y"] for bucket in buckets["fr"]), 0)

    def test_a_language_collected_for_less_than_4_weeks_is_noted(self):
        notes = {lang["code"]: lang["note"] for lang in self._payload(date(2026, 11, 3))["languages"]}
        self.assertEqual(notes["ja"], "Collected since 2 November 2026")
        self.assertIsNone(notes["en"])

        later = {lang["code"]: lang["note"] for lang in self._payload(date(2026, 11, 30))["languages"]}
        self.assertIsNone(later["ja"])
