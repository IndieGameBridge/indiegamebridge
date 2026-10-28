"""Tests for exporting a search's results (/api/streamers/export/<format>/?<search>)."""

import csv
import io
import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.exports.models import Export
from apps.exports.views import SearchExportView
from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch

User = get_user_model()


@override_settings(FRONTEND_URL="https://indiegamebridge.test")
class SearchExportTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()
        cache.clear()  # the throttle counters live there

        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        # Inside the form's default filters, so an empty query finds all three.
        for host_user_id, login, peak in ((1, "middle", 100), (2, "top", 150), (3, "small", 60)):
            self._make_streamer(host_user_id, login, peak)

    def _make_streamer(self, host_user_id, login, peak, language="en"):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )
        StreamerSearchStats.objects.create(
            streamer_profile=profile,
            language=language,
            peak_viewers=peak,
            avg_viewers=50,
            total_duration_seconds=36000,
            streams_count=8,
            genre_ids=[],
            host_login=login,
            host_display_name=login.title(),
        )
        return profile

    def _export(self, query="", file_format="json", user=None):
        request = self.factory.get(f"/api/streamers/export/{file_format}/?{query}")
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return SearchExportView.as_view()(request, file_format=file_format)

    def test_exports_every_match_in_result_order(self):
        streamers = json.loads(self._export().content)["streamers"]

        self.assertEqual([streamer["twitch_login"] for streamer in streamers], ["top", "middle", "small"])
        self.assertEqual(streamers[0]["twitch_user_id"], "2")
        self.assertEqual((streamers[0]["language"], streamers[0]["max_viewers"]), ("English", 150))

    def test_exports_only_what_the_filters_let_through(self):
        self._make_streamer(4, "french", 100, language="fr")

        streamers = json.loads(self._export("peakmax=75").content)["streamers"]

        self.assertEqual([streamer["twitch_login"] for streamer in streamers], ["small"])

    def test_has_no_list_columns(self):
        header = next(csv.reader(io.StringIO(self._export(file_format="csv").content.decode("utf-8-sig"))))

        self.assertEqual(header[0], "Twitch login")
        self.assertNotIn("Note", header)

    def test_links_back_to_the_same_search_with_every_filter_spelled_out(self):
        data = json.loads(self._export("peakmax=any").content)

        url = urlsplit(data["url"])
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", "https://indiegamebridge.test/streamers")
        query = parse_qs(url.query)
        # "any" is kept, or the link would come back capped at the form's default.
        self.assertEqual((query["lang"], query["peakmax"], query["peakmin"]), (["en"], ["any"], ["5"]))
        self.assertIn({"label": "Language", "value": "English"}, data["search"])
        self.assertIsNone(data["title"])

    def test_names_the_file_after_the_search_language(self):
        response = self._export("lang=en", file_format="xlsx")

        self.assertRegex(
            response["Content-Disposition"],
            r'^attachment; filename="indiegamebridge-search-en-\d{4}-\d{2}-\d{2}\.xlsx"$',
        )

    def test_records_the_search_it_exported(self):
        self._export("peakmax=any", file_format="xlsx")

        export = Export.objects.get()
        self.assertEqual((export.source, export.file_format, export.rows), ("search", "xlsx", 3))
        self.assertIsNone(export.list_of_streamers)
        self.assertEqual(export.search_filters, StreamerSearch({"peakmax": "any"}).explicit_filters())

    def test_requires_authentication(self):
        self.assertIn(self._export(user=False).status_code, (401, 403))
        self.assertFalse(Export.objects.exists())
