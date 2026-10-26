"""Tests for one list: reading it with its entries, editing it, deleting it (/api/lists/<id>/)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.streams.models import StreamerProfile, StreamerSearchStats
from apps.streams.search import PAGE_SIZE, StreamerSearch
from apps.userlists.models import StreamerInList, UserLabelForListOfStreamers, UserListOfStreamers
from apps.userlists.views import ListDetailView

User = get_user_model()


class ListDetailTests(TestCase):
    def setUp(self):
        # Both are process-cached; clear so this class builds them from its own
        # rows rather than a prior test's snapshot.
        StreamerSearch.get_filters_config.cache_clear()
        StreamerSearch._genre_name_map.cache_clear()

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

    def _get(self, list_id=None, user=None, offset=None):
        list_id = list_id or self.list.id
        request = self.factory.get(f"/api/lists/{list_id}/", {} if offset is None else {"offset": offset})
        return self._send(request, list_id, user)

    def _patch(self, payload, list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.patch(f"/api/lists/{list_id}/", payload, format="json")
        return self._send(request, list_id, user)

    def _delete(self, list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.delete(f"/api/lists/{list_id}/")
        return self._send(request, list_id, user)

    def _send(self, request, list_id, user):
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListDetailView.as_view()(request, list_id=list_id)

    def test_returns_the_entries_in_saved_order_with_their_stats(self):
        for index, login in enumerate(("top", "middle", "small"), start=1):
            self._add(self._make_streamer(index, login), description=f"note on {login}")

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["streamers_count"], 3)
        entries = response.data["entries"]
        self.assertEqual(
            [entry["streamer"]["login"] for entry in entries], ["top", "middle", "small"],
        )
        self.assertEqual(entries[0]["description"], "note on top")
        self.assertEqual(
            entries[0]["streamer"]["stats"],
            {"peak_viewers": 100, "avg_viewers": 50, "streams_count": 8, "hours_streamed": 10, "genres": []},
        )

    def test_stats_come_from_the_lists_language(self):
        # The list was searched in English. A streamer who now only streams in
        # French stays in it, just without numbers to show.
        self._add(self._make_streamer(1, "bilingual", languages=("en", "fr")))
        self._add(self._make_streamer(2, "moved_on", languages=("fr",)))

        entries = self._get().data["entries"]

        self.assertIsNotNone(entries[0]["streamer"]["stats"])
        self.assertIsNone(entries[1]["streamer"]["stats"])

    def test_an_opted_out_streamer_comes_back_anonymized_with_its_note(self):
        streamer = self._make_streamer(1, "gone")
        self._add(streamer, description="replied 3 Sep, wants a key")
        streamer.delete()

        (entry,) = self._get().data["entries"]

        self.assertIsNone(entry["streamer"])
        self.assertEqual(entry["description"], "replied 3 Sep, wants a key")

    def test_pages_through_the_entries(self):
        for index in range(PAGE_SIZE + 1):
            self._add(self._make_streamer(index + 1, f"streamer{index}", languages=()))

        first = self._get().data
        second = self._get(offset=PAGE_SIZE).data

        self.assertEqual(len(first["entries"]), PAGE_SIZE)
        self.assertEqual(
            [entry["streamer"]["login"] for entry in second["entries"]], [f"streamer{PAGE_SIZE}"],
        )
        self.assertEqual(second["streamers_count"], PAGE_SIZE + 1)

    def test_a_page_starts_at_any_offset(self):
        # After removing one of the first page's entries, the next page has to
        # start one earlier, or the entry that moved up would never be shown.
        for index in range(3):
            self._add(self._make_streamer(index + 1, f"streamer{index}", languages=()))

        entries = self._get(offset=1).data["entries"]

        self.assertEqual(
            [entry["streamer"]["login"] for entry in entries], ["streamer1", "streamer2"],
        )

    def test_a_bad_offset_reads_from_the_start(self):
        self._add(self._make_streamer(1, "first", languages=()))

        for bad_offset in ("abc", "-5"):
            with self.subTest(offset=bad_offset):
                (entry,) = self._get(offset=bad_offset).data["entries"]
                self.assertEqual(entry["streamer"]["login"], "first")

    def test_an_offset_past_the_end_is_an_empty_page(self):
        self._add(self._make_streamer(1, "first", languages=()))

        for offset in ("1", "99999999999999999999999"):
            with self.subTest(offset=offset):
                response = self._get(offset=offset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["entries"], [])

    def test_describes_the_search_it_was_saved_from(self):
        data = self._get().data

        self.assertTrue(data["from_search"])
        self.assertIn({"label": "Language", "value": "English"}, data["search"])
        # No max was set, so the summary shows an open-ended range.
        self.assertIn({"label": "Max Viewers", "value": "5+"}, data["search"])

    def test_a_list_made_by_hand_shows_each_streamer_in_their_main_language(self):
        by_hand = self._make_list(self.user)
        streamer = self._make_streamer(1, "bilingual", languages=("en", "fr"))
        # More hours in French, so French is the one to show.
        StreamerSearchStats.objects.filter(streamer_profile=streamer, language="fr").update(
            total_duration_seconds=72000, peak_viewers=300,
        )
        self._add(streamer, list_of_streamers=by_hand)

        data = self._get(list_id=by_hand.id).data

        self.assertFalse(data["from_search"])
        self.assertEqual(data["search"], [])
        stats = data["entries"][0]["streamer"]["stats"]
        self.assertEqual(stats["language"], "French")
        self.assertEqual((stats["peak_viewers"], stats["hours_streamed"]), (300, 20))

    def test_a_list_made_by_hand_has_no_stats_for_a_streamer_gone_quiet(self):
        by_hand = self._make_list(self.user)
        self._add(self._make_streamer(1, "quiet", languages=()), list_of_streamers=by_hand)

        (entry,) = self._get(list_id=by_hand.id).data["entries"]

        self.assertIsNone(entry["streamer"]["stats"])

    def test_edits_the_title_and_note(self):
        response = self._patch({"title": "  to contact  ", "description": "for the demo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "to contact")
        self.list.refresh_from_db()
        self.assertEqual((self.list.title, self.list.description), ("to contact", "for the demo"))

    def test_edits_only_the_fields_sent(self):
        self._patch({"description": "keep me"})

        self._patch({"title": "renamed"})

        self.list.refresh_from_db()
        self.assertEqual((self.list.title, self.list.description), ("renamed", "keep me"))

    def test_rejects_a_blank_title_or_overlong_text(self):
        for payload in ({"title": "   "}, {"title": "t" * 33}, {"description": "d" * 513}):
            with self.subTest(payload=payload):
                self.assertEqual(self._patch(payload).status_code, 400)

        self.list.refresh_from_db()
        self.assertEqual((self.list.title, self.list.description), ("small streamers", ""))

    def test_deletes_the_list_with_its_entries_but_not_its_labels(self):
        label = UserLabelForListOfStreamers.objects.create(owner=self.user, title="shooters", color="#0072B2")
        self.list.labels.add(label)
        entry = self._add(self._make_streamer(1, "top"), description="replied, wants a key")

        response = self._delete()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(UserListOfStreamers.objects.filter(id=self.list.id).exists())
        self.assertFalse(StreamerInList.objects.filter(id=entry.id).exists())
        self.assertTrue(UserLabelForListOfStreamers.objects.filter(id=label.id).exists())
        self.assertTrue(StreamerProfile.objects.filter(host_login="top").exists())

    def test_another_users_list_cannot_be_edited_or_deleted(self):
        theirs = self._make_list(self.other, search={"lang": "en"})

        self.assertEqual(self._patch({"title": "mine now"}, list_id=theirs.id).status_code, 404)
        self.assertEqual(self._delete(list_id=theirs.id).status_code, 404)

        theirs.refresh_from_db()
        self.assertEqual(theirs.title, "small streamers")

    def test_editing_and_deleting_require_authentication(self):
        self.assertIn(self._patch({"title": "renamed"}, user=False).status_code, (401, 403))
        self.assertIn(self._delete(user=False).status_code, (401, 403))

        self.list.refresh_from_db()
        self.assertEqual(self.list.title, "small streamers")

    def test_another_users_list_is_not_found(self):
        theirs = self._make_list(self.other, search={"lang": "en"})

        # Same answer as a list that doesn't exist, so ids can't be probed.
        self.assertEqual(self._get(list_id=theirs.id).status_code, 404)
        self.assertEqual(self._get(list_id=theirs.id + 1000).status_code, 404)

    def test_requires_authentication(self):
        self.assertIn(self._get(user=False).status_code, (401, 403))
