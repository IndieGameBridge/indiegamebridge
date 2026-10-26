"""Tests for reading the owner's lists (GET /api/lists/), which feeds the dashboard cards."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle

from apps.streams.models import StreamerProfile
from apps.userlists.models import (
    StreamerInList,
    UserLabelForListOfStreamers,
    UserListOfStreamers,
)
from apps.userlists.views.lists import ListsView

User = get_user_model()


class GetListsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")

    def _get(self, user=None, **params):
        request = self.factory.get("/api/lists/", params)
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListsView.as_view()(request)

    def _post(self):
        request = self.factory.post(
            "/api/lists/", {"title": "small streamers", "search": "lang=en"}, format="json",
        )
        force_authenticate(request, user=self.user)
        return ListsView.as_view()(request)

    def _make_list(self, title, owner=None, **fields):
        return UserListOfStreamers.objects.create(owner=owner or self.user, title=title, **fields)

    def _make_label(self, title, color):
        return UserLabelForListOfStreamers.objects.create(owner=self.user, title=title, color=color)

    def _add_streamer(self, list_of_streamers, host_user_id):
        profile = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=f"streamer{host_user_id}",
            host_display_name=f"Streamer{host_user_id}",
        )
        StreamerInList.objects.create(list_of_streamers=list_of_streamers, streamer_profile=profile)
        return profile

    def test_returns_only_the_owners_lists_newest_first(self):
        for title in ("first", "second", "third"):
            self._make_list(title)
        self._make_list("theirs", owner=self.other)

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [card["title"] for card in response.data["lists"]], ["third", "second", "first"],
        )

    def test_a_card_carries_its_labels_and_streamer_count(self):
        shooters = self._make_label("shooters", "#0072B2")
        priority = self._make_label("priority", "#D55E00")
        pitched = self._make_list("pitched", description="for the shooter pitch")
        pitched.labels.set([shooters, priority])
        self._add_streamer(pitched, 1)
        self._add_streamer(pitched, 2)
        # An opted-out streamer's entry stays in the list, so it still counts.
        self._add_streamer(pitched, 3).delete()
        self._make_list("bare")

        cards = {card["title"]: card for card in self._get().data["lists"]}

        self.assertEqual(cards["pitched"]["id"], pitched.id)
        self.assertEqual(cards["pitched"]["description"], "for the shooter pitch")
        self.assertEqual(cards["pitched"]["streamers_count"], 3)
        self.assertEqual(cards["pitched"]["created_at"], pitched.created_at.isoformat())
        # Alphabetical, the labels' own ordering.
        self.assertEqual(
            cards["pitched"]["labels"],
            [
                {"id": priority.id, "title": "priority", "color": "#D55E00"},
                {"id": shooters.id, "title": "shooters", "color": "#0072B2"},
            ],
        )
        # Counts and labels stay with the list they belong to.
        self.assertEqual(cards["bare"]["streamers_count"], 0)
        self.assertEqual(cards["bare"]["labels"], [])
        # Only asked for by the add-to-list menus.
        self.assertNotIn("contains", cards["pitched"])

    def test_contains_marks_the_lists_holding_a_streamer(self):
        holding = self._make_list("holding")
        streamer = self._add_streamer(holding, 1)
        self._add_streamer(self._make_list("others"), 2)
        self._make_list("bare")

        response = self._get(contains=streamer.id)

        self.assertEqual(response.status_code, 200)
        # Every list comes back, marked rather than filtered.
        self.assertEqual(
            {card["title"]: card["contains"] for card in response.data["lists"]},
            {"holding": True, "others": False, "bare": False},
        )

    def test_rejects_a_contains_that_is_not_an_id(self):
        self._make_list("bare")

        self.assertEqual(self._get(contains="top").status_code, 400)

    def test_a_user_without_lists_gets_an_empty_collection(self):
        self._make_list("theirs", owner=self.other)

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"lists": []})

    def test_requires_authentication(self):
        response = self._get(user=False)

        self.assertIn(response.status_code, (401, 403))

    def test_only_creating_spends_the_write_budget(self):
        # The dashboard reads this on every visit; if reads shared the tight write
        # rate, browsing it would lock the user out of saving a list.
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"userlists_write": "1/hour"}):
            for _ in range(3):
                self.assertEqual(self._get().status_code, 200)
            self.assertEqual(self._post().status_code, 201)
            self.assertEqual(self._post().status_code, 429)
