"""Tests for one entry of a list (/api/lists/<id>/entries/<id>/): its note, and removing it."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.streams.models import StreamerProfile
from apps.userlists.models import StreamerInList, UserListOfStreamers
from apps.userlists.views import ListEntryView
from apps.userlists.views.list_entry import MAX_NOTE

User = get_user_model()


class ListEntryTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="dev")
        self.other = User.objects.create_user(username="other")
        self.list = UserListOfStreamers.objects.create(owner=self.user, title="small streamers")
        self.streamer = StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=1,
            host_login="solo",
            host_display_name="Solo",
        )
        self.entry = StreamerInList.objects.create(
            list_of_streamers=self.list, streamer_profile=self.streamer,
        )

    def _patch(self, description, list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.patch(
            f"/api/lists/{list_id}/entries/{self.entry.id}/",
            {"description": description},
            format="json",
        )
        return self._send(request, list_id, user)

    def _delete(self, list_id=None, user=None):
        list_id = list_id or self.list.id
        request = self.factory.delete(f"/api/lists/{list_id}/entries/{self.entry.id}/")
        return self._send(request, list_id, user)

    def _send(self, request, list_id, user):
        if user is not False:
            force_authenticate(request, user=user or self.user)
        return ListEntryView.as_view()(request, list_id=list_id, entry_id=self.entry.id)

    def test_the_owner_can_write_a_note(self):
        response = self._patch("  replied 3 Sep, wants a key  ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "replied 3 Sep, wants a key")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, "replied 3 Sep, wants a key")

    def test_an_empty_note_clears_it(self):
        self.entry.description = "old note"
        self.entry.save()

        self.assertEqual(self._patch("").status_code, 200)

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, "")

    def test_rejects_an_over_long_note(self):
        response = self._patch("n" * (MAX_NOTE + 1))

        self.assertEqual(response.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, "")

    def test_another_users_entry_is_not_found(self):
        self.assertEqual(self._patch("mine now", user=self.other).status_code, 404)

    def test_the_entry_must_belong_to_the_list_in_the_url(self):
        other_list = UserListOfStreamers.objects.create(owner=self.user, title="shooters")

        self.assertEqual(self._patch("moved", list_id=other_list.id).status_code, 404)

    def test_requires_authentication(self):
        self.assertIn(self._patch("anon", user=False).status_code, (401, 403))

    def test_the_owner_can_remove_a_streamer_from_the_list(self):
        response = self._delete()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(StreamerInList.objects.filter(id=self.entry.id).exists())
        # Only the membership goes; the streamer and the list stay.
        self.assertTrue(StreamerProfile.objects.filter(id=self.streamer.id).exists())
        self.assertTrue(UserListOfStreamers.objects.filter(id=self.list.id).exists())

    def test_an_anonymized_entry_can_be_removed(self):
        self.streamer.delete()

        self.assertEqual(self._delete().status_code, 204)
        self.assertFalse(StreamerInList.objects.exists())

    def test_another_users_entry_cannot_be_removed(self):
        self.assertEqual(self._delete(user=self.other).status_code, 404)

        other_list = UserListOfStreamers.objects.create(owner=self.user, title="shooters")
        self.assertEqual(self._delete(list_id=other_list.id).status_code, 404)

        self.assertTrue(StreamerInList.objects.filter(id=self.entry.id).exists())

    def test_removing_requires_authentication(self):
        self.assertIn(self._delete(user=False).status_code, (401, 403))
        self.assertTrue(StreamerInList.objects.filter(id=self.entry.id).exists())
