from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.userlists.models import UserLabelForListOfStreamers


class UserLabelForListOfStreamersTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="dev", password="x")
        self.other = User.objects.create_user(username="other", password="x")

    def _make_label(self, owner=None, title="shooters", color="#0072B2"):
        return UserLabelForListOfStreamers.objects.create(
            owner=owner or self.owner, title=title, color=color,
        )

    def test_same_title_allowed_with_different_colors(self):
        # The colour is half the label: "priority" in red and in green is a
        # deliberate pair, not a duplicate.
        self._make_label(title="priority", color="#D55E00")
        self._make_label(title="priority", color="#009E73")

        self.assertEqual(
            UserLabelForListOfStreamers.objects.filter(title="priority").count(), 2,
        )

    def test_same_title_allowed_for_different_owners(self):
        self._make_label(owner=self.owner, title="shooters")
        self._make_label(owner=self.other, title="shooters")

        self.assertEqual(UserLabelForListOfStreamers.objects.count(), 2)

    def test_color_must_be_six_digit_hex(self):
        for bad_color in ("red", "#fff", "0072B2", "#0072B", "#0072B2FF"):
            with self.subTest(color=bad_color):
                label = UserLabelForListOfStreamers(
                    owner=self.owner, title="shooters", color=bad_color,
                )
                with self.assertRaises(ValidationError):
                    label.full_clean()

    def test_color_accepts_either_case(self):
        for index, good_color in enumerate(("#0072B2", "#0072b2")):
            with self.subTest(color=good_color):
                label = UserLabelForListOfStreamers(
                    owner=self.owner, title=f"label{index}", color=good_color,
                )
                label.full_clean()

    def test_labels_are_ordered_alphabetically(self):
        self._make_label(title="shooters")
        self._make_label(title="puzzles")
        self._make_label(title="cozy")

        titles = list(
            UserLabelForListOfStreamers.objects
            .filter(owner=self.owner)
            .values_list("title", flat=True)
        )

        self.assertEqual(titles, ["cozy", "puzzles", "shooters"])

    def test_labels_are_removed_with_their_owner(self):
        self._make_label(owner=self.other)

        self.other.delete()

        self.assertFalse(UserLabelForListOfStreamers.objects.exists())
