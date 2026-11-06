"""JSON that isn't an object is turned away at the parser, whichever view would have read it."""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.userlists.models import StreamerInList, UserListOfStreamers

User = get_user_model()

NOT_OBJECTS = (["search"], "title", 5, True, None)


class JsonObjectParserTests(TestCase):
    def setUp(self):
        # The throttles count in the cache, which outlives a test.
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.user = User.objects.create_user(username="dev")
        self.client.force_authenticate(self.user)
        self.list = UserListOfStreamers.objects.create(owner=self.user, title="small streamers")
        self.entry = StreamerInList.objects.create(list_of_streamers=self.list)

    def _send(self, method, url, body):
        return getattr(self.client, method)(url, json.dumps(body), content_type="application/json")

    def _assert_refused(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Expected a JSON object."})

    def test_the_list_writes_refuse_it(self):
        writes = (
            ("post", "/api/lists/"),
            ("patch", f"/api/lists/{self.list.id}/"),
            # This one's throttle reads the body before the view does.
            ("post", f"/api/lists/{self.list.id}/entries/"),
            ("patch", f"/api/lists/{self.list.id}/entries/{self.entry.id}/"),
        )
        for method, url in writes:
            for body in NOT_OBJECTS:
                with self.subTest(url=url, body=body):
                    self._assert_refused(self._send(method, url, body))

    def test_the_other_views_refuse_it_too(self):
        self._assert_refused(self._send("patch", "/auth/settings/", ["allow_tracking"]))
        self._assert_refused(self._send("post", "/api/contact/", ["name"]))

    def test_an_object_still_reaches_the_view(self):
        response = self._send("patch", f"/api/lists/{self.list.id}/", {"title": "renamed"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "renamed")
