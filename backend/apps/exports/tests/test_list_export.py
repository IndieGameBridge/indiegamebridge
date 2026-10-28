"""Tests for exporting one of the user's lists (/api/lists/<id>/export/<format>/)."""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle

from apps.exports.models import Export
from apps.exports.views import ListExportView
from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import PAGE_SIZE, StreamerSearch
from apps.userlists.models import StreamerInList, UserListOfStreamers
from apps.users.models import AccountSettings

User = get_user_model()


@override_settings(FRONTEND_URL="https://indiegamebridge.test")
class ListExportTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()
        cache.clear()  # the throttle counters live there

        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")
        self.list = self._make_list(self.user, search={"lang": "en", "peakmax": "any"})

    def _make_list(self, owner, search=None):
        return UserListOfStreamers.objects.create(
            owner=owner,
            title="small streamers",
            search_filters=StreamerSearch(search).explicit_filters() if search else {},
        )

    def _make_streamer(self, host_user_id, login, languages=("en",)):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )
        for language in languages:
            StreamerSearchStats.objects.create(
                streamer_profile=profile,
                language=language,
                peak_viewers=100,
                avg_viewers=50,
                total_duration_seconds=36000,
                streams_count=8,
                genre_ids=[],
                host_login=login,
                host_display_name=login.title(),
            )
        return profile

    def _add(self, profile, list_of_streamers=None, description=""):
        return StreamerInList.objects.create(
            list_of_streamers=list_of_streamers or self.list,
            streamer_profile=profile,
            description=description,
        )

    def _export(self, file_format="json", list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.get(f"/api/lists/{list_id}/export/{file_format}/")
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListExportView.as_view()(request, list_id=list_id, file_format=file_format)

    def _streamers(self, list_id=None):
        return json.loads(self._export(list_id=list_id).content)["streamers"]

    def test_exports_every_entry_in_saved_order_with_stats_and_notes(self):
        for index, login in enumerate(("top", "middle", "small"), start=1):
            self._add(self._make_streamer(index, login), description=f"note on {login}")

        streamers = self._streamers()

        self.assertEqual([streamer["twitch_login"] for streamer in streamers], ["top", "middle", "small"])
        first = streamers[0]
        self.assertEqual(first["twitch_url"], "https://www.twitch.tv/top")
        self.assertEqual(first["twitch_user_id"], "1")
        self.assertEqual(first["language"], "English")
        self.assertEqual((first["max_viewers"], first["avg_viewers"], first["hours_streamed"]), (100, 50, 10))
        self.assertEqual(first["note"], "note on top")

    def test_exports_the_whole_list_not_a_page_of_it(self):
        for index in range(PAGE_SIZE + 1):
            self._add(self._make_streamer(index + 1, f"streamer{index}", languages=()))

        self.assertEqual(len(self._streamers()), PAGE_SIZE + 1)

    def test_stats_come_from_the_lists_language(self):
        self._add(self._make_streamer(1, "moved_on", languages=("fr",)))

        (streamer,) = self._streamers()

        self.assertEqual(streamer["twitch_login"], "moved_on")
        self.assertIsNone(streamer["max_viewers"])

    def test_a_list_made_by_hand_shows_each_streamer_in_their_main_language(self):
        by_hand = self._make_list(self.user)
        self._add(self._make_streamer(1, "bilingual", languages=("fr",)), list_of_streamers=by_hand)

        (streamer,) = self._streamers(list_id=by_hand.id)

        self.assertEqual(streamer["language"], "French")

    def test_an_opted_out_streamer_keeps_only_the_note(self):
        streamer = self._make_streamer(1, "gone")
        self._add(streamer, description="replied 3 Sep, wants a key")
        streamer.delete()

        (row,) = self._streamers()

        self.assertIsNone(row["twitch_login"])
        self.assertIsNone(row["twitch_url"])
        self.assertEqual(row["note"], "replied 3 Sep, wants a key")

    def test_links_back_to_the_list(self):
        data = json.loads(self._export().content)

        self.assertEqual(data["url"], f"https://indiegamebridge.test/lists/{self.list.id}")
        self.assertEqual(data["title"], "small streamers")
        self.assertIn({"label": "Language", "value": "English"}, data["search"])

    def test_each_format_downloads_as_a_file_named_after_the_list(self):
        content_types = {
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv; charset=utf-8",
            "json": "application/json",
        }
        for file_format, content_type in content_types.items():
            with self.subTest(file_format=file_format):
                response = self._export(file_format)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], content_type)
                self.assertRegex(
                    response["Content-Disposition"],
                    rf'^attachment; filename="indiegamebridge-small-streamers-\d{{4}}-\d{{2}}-\d{{2}}\.{file_format}"$',
                )

    def test_no_shared_cache_keeps_the_file(self):
        self.assertIn("no-store", self._export()["Cache-Control"])

    def test_an_unknown_format_is_not_found(self):
        self.assertEqual(self._export("xml").status_code, 404)
        self.assertFalse(Export.objects.exists())

    def test_another_users_list_is_not_found(self):
        theirs = self._make_list(self.other, search={"lang": "en"})

        # Same answer as a list that doesn't exist, so ids can't be probed.
        self.assertEqual(self._export(list_id=theirs.id).status_code, 404)
        self.assertEqual(self._export(list_id=theirs.id + 1000).status_code, 404)

    def test_requires_authentication(self):
        self.assertIn(self._export(user=False).status_code, (401, 403))

    def test_records_the_export(self):
        self._add(self._make_streamer(1, "top"))

        self._export("csv")

        export = Export.objects.get()
        self.assertEqual((export.user, export.source, export.list_of_streamers), (self.user, "list", self.list))
        self.assertEqual((export.file_format, export.rows), ("csv", 1))

    def test_records_nothing_for_a_user_who_turned_tracking_off(self):
        AccountSettings.objects.create(user=self.user, allow_tracking=False)

        self.assertEqual(self._export().status_code, 200)
        self.assertFalse(Export.objects.exists())

    def test_the_file_still_downloads_when_recording_it_fails(self):
        with mock.patch.object(Export.objects, "create", side_effect=RuntimeError("db down")):
            with self.assertLogs("apps.exports", level="ERROR"):
                response = self._export()

        self.assertEqual(response.status_code, 200)

    def test_exports_have_an_hourly_limit_of_their_own(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"exports": "2/hour"}):
            self.assertEqual(self._export().status_code, 200)
            self.assertEqual(self._export("csv").status_code, 200)
            response = self._export("xlsx")

        self.assertEqual(response.status_code, 429)
        # The menu reads this to say when to try again.
        self.assertIn("Retry-After", response)
