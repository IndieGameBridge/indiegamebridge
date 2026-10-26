from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.userlists.models import UserLabelForListOfStreamers, UserListOfStreamers


class UserListOfStreamersTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="dev", password="x")
        self.other = User.objects.create_user(username="other", password="x")

    def _make_list(self, owner=None, title="small streamers", description=""):
        return UserListOfStreamers.objects.create(
            owner=owner or self.owner, title=title, description=description,
        )

    def _make_label(self, owner=None, title="shooters", color="#0072B2"):
        return UserLabelForListOfStreamers.objects.create(
            owner=owner or self.owner, title=title, color=color,
        )

    def test_description_is_optional(self):
        one_list = self._make_list()

        one_list.full_clean()

        self.assertEqual(one_list.description, "")

    def test_title_and_description_lengths_are_enforced(self):
        too_long = UserListOfStreamers(owner=self.owner, title="t" * 33)
        with self.assertRaises(ValidationError):
            too_long.full_clean()

        wordy = UserListOfStreamers(owner=self.owner, title="ok", description="d" * 513)
        with self.assertRaises(ValidationError):
            wordy.full_clean()

    def test_labels_can_be_attached(self):
        one_list = self._make_list()
        shooters = self._make_label(title="shooters")
        priority = self._make_label(title="priority", color="#D55E00")

        one_list.labels.add(shooters, priority)

        self.assertCountEqual(
            one_list.labels.values_list("title", flat=True), ["shooters", "priority"],
        )
        self.assertEqual(list(shooters.lists.all()), [one_list])

    def test_deleting_a_label_leaves_the_list(self):
        one_list = self._make_list()
        label = self._make_label()
        one_list.labels.add(label)

        label.delete()

        one_list.refresh_from_db()
        self.assertEqual(one_list.labels.count(), 0)

    def test_lists_are_ordered_newest_first(self):
        self._make_list(title="first")
        self._make_list(title="second")
        self._make_list(title="third")

        titles = list(
            UserListOfStreamers.objects
            .filter(owner=self.owner)
            .values_list("title", flat=True)
        )

        self.assertEqual(titles, ["third", "second", "first"])

    def test_lists_are_removed_with_their_owner(self):
        self._make_list(owner=self.other)

        self.other.delete()

        self.assertFalse(UserListOfStreamers.objects.exists())
