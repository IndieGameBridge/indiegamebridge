"""Unit tests for the Helix client."""

from unittest import mock

from django.test import SimpleTestCase

from core.utils.twitch_api_client import StreamTuple, TwitchApiClient


def _make_raw_stream(**overrides):
    """Build a Helix /streams response entry with all fields populated.

    Helix returns ID fields as strings (numeric content); the client is responsible
    for converting them to int before they leave the boundary.
    """
    defaults = {
        "id": "1001",
        "user_id": "2001",
        "user_login": "loginx",
        "user_name": "DisplayName",
        "game_id": "3001",
        "viewer_count": 100,
        "started_at": "2025-01-01T00:00:00Z",
        "type": "live",
    }
    defaults.update(overrides)
    return defaults


class TwitchApiClientIterStreamsTests(SimpleTestCase):
    """
    `__init__` opens a real ``httpx.Client``, which we don't need here — the
    pagination loop only touches ``self.get_streams``. Constructing via
    ``__new__`` skips that and keeps the test focused on the loop.
    """

    def _client(self):
        return TwitchApiClient.__new__(TwitchApiClient)

    def test_paginates_until_no_cursor(self):
        client = self._client()
        pages = [
            {
                "data": [_make_raw_stream(id="1"), _make_raw_stream(id="2", user_id="22")],
                "pagination": {"cursor": "abc"},
            },
            {
                "data": [_make_raw_stream(id="3", user_id="33")],
                "pagination": {"cursor": "def"},
            },
            {
                "data": [_make_raw_stream(id="4", user_id="44")],
                "pagination": {},
            },
        ]
        with mock.patch.object(client, "get_streams", side_effect=pages) as gs:
            streams, cursor = client.iter_streams(
                language="en", end_time_anchor=10**12
            )

        self.assertEqual([s.host_stream_id for s in streams], [1, 2, 3, 4])
        self.assertIsNone(cursor)
        self.assertEqual(
            [c.kwargs.get("after") for c in gs.call_args_list],
            [None, "abc", "def"],
        )

    def test_returns_cursor_when_max_requests_reached(self):
        """When max_requests caps the loop, the next cursor is returned for resumption."""
        client = self._client()
        pages = [
            {"data": [_make_raw_stream(id="1")], "pagination": {"cursor": "abc"}},
            {"data": [_make_raw_stream(id="2", user_id="22")], "pagination": {"cursor": "def"}},
        ]
        with mock.patch.object(client, "get_streams", side_effect=pages):
            streams, cursor = client.iter_streams(
                language="en", end_time_anchor=10**12, max_requests=2
            )

        self.assertEqual([s.host_stream_id for s in streams], [1, 2])
        self.assertEqual(cursor, "def")

    def test_stops_when_cursor_is_empty_string(self):
        client = self._client()
        page = {"data": [_make_raw_stream()], "pagination": {"cursor": ""}}
        with mock.patch.object(client, "get_streams", return_value=page) as gs:
            streams, cursor = client.iter_streams(
                language="en", end_time_anchor=10**12
            )

        self.assertEqual(len(streams), 1)
        self.assertEqual(cursor, "")
        gs.assert_called_once()

    def test_stops_when_pagination_key_missing(self):
        client = self._client()
        page = {"data": [_make_raw_stream()]}
        with mock.patch.object(client, "get_streams", return_value=page) as gs:
            streams, cursor = client.iter_streams(
                language="en", end_time_anchor=10**12
            )

        self.assertEqual(len(streams), 1)
        self.assertIsNone(cursor)
        gs.assert_called_once()

    def test_stops_when_deadline_exceeded(self):
        """end_time_anchor=0 with positive time.time() means the loop bails after page 1."""
        client = self._client()
        pages = [
            {"data": [_make_raw_stream(id="1")], "pagination": {"cursor": "abc"}},
            {"data": [_make_raw_stream(id="2", user_id="22")], "pagination": {"cursor": "def"}},
        ]
        with mock.patch.object(client, "get_streams", side_effect=pages) as gs:
            streams, cursor = client.iter_streams(language="en", end_time_anchor=0)

        self.assertEqual([s.host_stream_id for s in streams], [1])
        self.assertEqual(cursor, "abc")
        gs.assert_called_once()

    def test_filters_out_entries_with_missing_fields(self):
        """Entries missing any required field land as None and must be dropped."""
        client = self._client()
        full = _make_raw_stream(id="500")
        missing_user_id = _make_raw_stream(id="600")
        missing_user_id.pop("user_id")
        page = {
            "data": [full, missing_user_id],
            "pagination": {},
        }
        with mock.patch.object(client, "get_streams", return_value=page):
            streams, _ = client.iter_streams(language="en", end_time_anchor=10**12)

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].host_stream_id, 500)

    def test_skips_stream_with_non_numeric_id(self):
        """Helix is documented to return numeric ID strings; if it ever ships a non-numeric
        value, the client must skip the stream rather than crashing the poll round."""
        client = self._client()
        good = _make_raw_stream(id="700")
        bad = _make_raw_stream(id="ABC123")
        page = {
            "data": [good, bad],
            "pagination": {},
        }
        with mock.patch.object(client, "get_streams", return_value=page):
            streams, _ = client.iter_streams(language="en", end_time_anchor=10**12)

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].host_stream_id, 700)

    def test_builds_stream_tuple_from_raw_response(self):
        client = self._client()
        raw = _make_raw_stream(
            id="123",
            user_id="7",
            user_login="login7",
            user_name="Display 7",
            game_id="77",
            viewer_count=42,
            started_at="2025-06-01T12:00:00Z",
            type="live",
        )
        with mock.patch.object(client, "get_streams", return_value={"data": [raw], "pagination": {}}):
            streams, _ = client.iter_streams(language="en", end_time_anchor=10**12)

        self.assertEqual(len(streams), 1)
        self.assertEqual(
            streams[0],
            StreamTuple(
                status="live",
                host_stream_id=123,
                host_user_id=7,
                host_login="login7",
                host_display_name="Display 7",
                host_game_id=77,
                viewers=42,
                started_at="2025-06-01T12:00:00Z",
            ),
        )

    def test_keeps_streams_with_zero_viewers(self):
        """0 viewers is a count, not a missing field."""
        client = self._client()
        page = {"data": [_make_raw_stream(viewer_count=0)], "pagination": {}}
        with mock.patch.object(client, "get_streams", return_value=page):
            streams, _ = client.iter_streams(language="en", end_time_anchor=10**12)

        self.assertEqual([s.viewers for s in streams], [0])

    def test_stops_after_a_page_that_ends_under_min_viewers(self):
        """Helix sorts by viewers, so every page after one that ends under the
        minimum would be under it too: that page is the last one fetched."""
        client = self._client()
        pages = [
            {
                "data": [_make_raw_stream(id="1", viewer_count=50), _make_raw_stream(id="2", user_id="22", viewer_count=3)],
                "pagination": {"cursor": "abc"},
            },
            {
                "data": [_make_raw_stream(id="3", user_id="33", viewer_count=4), _make_raw_stream(id="4", user_id="44", viewer_count=2)],
                "pagination": {"cursor": "def"},
            },
            {
                "data": [_make_raw_stream(id="5", user_id="55", viewer_count=1)],
                "pagination": {},
            },
        ]
        with mock.patch.object(client, "get_streams", side_effect=pages) as gs:
            streams, cursor = client.iter_streams(
                language="en", end_time_anchor=10**12, min_viewers=3
            )

        # The page that crosses the minimum is kept whole.
        self.assertEqual([s.host_stream_id for s in streams], [1, 2, 3, 4])
        self.assertIsNone(cursor)
        self.assertEqual(gs.call_count, 2)


class TwitchApiClientStreamsByUserIdsTests(SimpleTestCase):
    """Constructed via ``__new__`` for the same reason as the iter_streams tests."""

    def _client(self):
        return TwitchApiClient.__new__(TwitchApiClient)

    def test_asks_for_the_given_streamers_and_parses_their_streams(self):
        client = self._client()
        response = mock.Mock()
        response.json.return_value = {"data": [_make_raw_stream(id="9", user_id="2", viewer_count=1)]}
        with mock.patch.object(client, "_request", return_value=response) as request:
            streams = client.get_streams_by_user_ids([1, 2])

        request.assert_called_once_with(
            "GET",
            "https://api.twitch.tv/helix/streams",
            params={"type": "live", "user_id": ["1", "2"], "first": 100},
        )
        self.assertEqual(
            [(s.host_stream_id, s.host_user_id, s.viewers) for s in streams],
            [(9, 2, 1)],
        )

    def test_no_streamers_means_no_request(self):
        client = self._client()
        with mock.patch.object(client, "_request") as request:
            self.assertEqual(client.get_streams_by_user_ids([]), [])

        request.assert_not_called()
