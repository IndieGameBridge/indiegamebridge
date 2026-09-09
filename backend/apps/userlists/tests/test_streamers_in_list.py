from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.streams.models import StreamerProfile
from apps.userlists.models import StreamerInList, UserListOfStreamers


class StreamerInListTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="dev", password="x")
        self.list_of_streamers = UserListOfStreamers.objects.create(
            owner=self.owner, title="small streamers",
        )

    def _make_streamer(self, host_user_id=1, login="alice"):
        return StreamerProfile.objects.create(
            host=StreamerProfile.Host.TWITCH,
            host_user_id=host_user_id,
            host_login=login,
            host_display_name=login.title(),
        )

    def _add(self, streamer, list_of_streamers=None, description=""):
        return StreamerInList.objects.create(
            list_of_streamers=list_of_streamers or self.list_of_streamers,
            streamer_profile=streamer,
            description=description,
        )

    def test_entry_survives_the_streamer_opting_out(self):
        streamer = self._make_streamer()
        entry = self._add(streamer, description="replied 3 Sep, wants a key")

        # What opt-out does: the profile row goes away.
        streamer.delete()

        entry.refresh_from_db()
        self.assertIsNone(entry.streamer_profile)
        self.assertEqual(entry.description, "replied 3 Sep, wants a key")

    def test_a_streamer_cannot_be_added_to_one_list_twice(self):
        streamer = self._make_streamer()
        self._add(streamer)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._add(streamer)

    def test_a_streamer_can_be_in_several_lists(self):
        streamer = self._make_streamer()
        other_list = UserListOfStreamers.objects.create(owner=self.owner, title="shooters")

        self._add(streamer)
        self._add(streamer, list_of_streamers=other_list)

        self.assertEqual(StreamerInList.objects.filter(streamer_profile=streamer).count(), 2)

    def test_several_anonymized_entries_can_share_a_list(self):
        first = self._make_streamer(host_user_id=1, login="alice")
        second = self._make_streamer(host_user_id=2, login="bob")
        self._add(first)
        self._add(second)

        first.delete()
        second.delete()

        # NULLs are distinct in Postgres, so the unique constraint doesn't collapse them.
        self.assertEqual(
            StreamerInList.objects.filter(streamer_profile__isnull=True).count(), 2,
        )

    def test_entries_are_removed_with_their_list(self):
        self._add(self._make_streamer())

        self.list_of_streamers.delete()

        self.assertFalse(StreamerInList.objects.exists())

    def test_entries_keep_the_order_they_were_added_in(self):
        for index, login in enumerate(("top", "middle", "small"), start=1):
            self._add(self._make_streamer(host_user_id=index, login=login))

        logins = list(
            self.list_of_streamers.entries.values_list("streamer_profile__host_login", flat=True)
        )

        # Saving a search writes the rows in result order, so the list reads back
        # ranked the way the user saw it.
        self.assertEqual(logins, ["top", "middle", "small"])
