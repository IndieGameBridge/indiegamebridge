"""Tests for login snapshots: signal wiring, IP extraction, geo lookup."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.users.geo import resolve_ip_location
from apps.users.models import AccountSettings, LoginSnapshot
from apps.users.signals import get_client_ip, record_login_snapshot

User = get_user_model()

# A genuinely global address - documentation ranges (203.0.113.x etc.) fail
# the is_global check in resolve_ip_location, which is what we want in prod
# but not what these tests are probing.
PUBLIC_IP = "8.8.8.8"


def _geo_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class RecordLoginSnapshotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="viewer", password="pw-test-123")

    def test_login_creates_snapshot(self):
        # End-to-end through the auth machinery proves the receiver is wired
        # up via UsersConfig.ready(), not just importable.
        self.assertTrue(self.client.login(username="viewer", password="pw-test-123"))
        snapshot = LoginSnapshot.objects.get()
        self.assertEqual(snapshot.user, self.user)
        self.assertIsNotNone(snapshot.created_at)
        # Django's own update_last_login receiver is disconnected; our
        # conditional call must cover for it.
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_receiver_records_ip_without_token(self):
        request = RequestFactory().get("/", REMOTE_ADDR=PUBLIC_IP)
        record_login_snapshot(sender=None, request=request, user=self.user)
        snapshot = LoginSnapshot.objects.get()
        self.assertEqual(snapshot.ip_address, PUBLIC_IP)
        self.assertEqual(snapshot.country_code, "")
        self.assertEqual(snapshot.city, "")

    @override_settings(IPINFO_API_TOKEN="test-token")
    def test_receiver_records_location_with_token(self):
        request = RequestFactory().get("/", REMOTE_ADDR=PUBLIC_IP)
        payload = {"country": "DE", "region": "Bavaria", "city": "Munich"}
        with mock.patch("apps.users.geo.httpx.get", return_value=_geo_response(payload)):
            record_login_snapshot(sender=None, request=request, user=self.user)
        snapshot = LoginSnapshot.objects.get()
        self.assertEqual(snapshot.country_code, "DE")
        self.assertEqual(snapshot.region, "Bavaria")
        self.assertEqual(snapshot.city, "Munich")

    def test_snapshot_failure_does_not_break_login(self):
        with mock.patch(
            "apps.users.signals.LoginSnapshot.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            self.assertTrue(self.client.login(username="viewer", password="pw-test-123"))
        self.assertEqual(LoginSnapshot.objects.count(), 0)


class TrackingGateTests(TestCase):
    """allow_tracking=False must suppress all login bookkeeping."""

    def setUp(self):
        self.user = User.objects.create_user(username="viewer", password="pw-test-123")

    def test_opted_out_user_gets_no_snapshot_and_no_last_login(self):
        AccountSettings.objects.create(user=self.user, allow_tracking=False)
        self.assertTrue(self.client.login(username="viewer", password="pw-test-123"))
        self.assertEqual(LoginSnapshot.objects.count(), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_login)

    def test_explicit_opt_in_records_snapshot_and_last_login(self):
        AccountSettings.objects.create(user=self.user, allow_tracking=True)
        self.assertTrue(self.client.login(username="viewer", password="pw-test-123"))
        self.assertEqual(LoginSnapshot.objects.count(), 1)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)


class GetClientIpTests(TestCase):
    factory = RequestFactory()

    @override_settings(NUM_PROXIES=1)
    def test_takes_rightmost_trusted_forwarded_address(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR=f"6.6.6.6, {PUBLIC_IP}", REMOTE_ADDR="10.0.0.1"
        )
        self.assertEqual(get_client_ip(request), PUBLIC_IP)

    @override_settings(NUM_PROXIES=0)
    def test_ignores_forgeable_header_without_proxies(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR=PUBLIC_IP
        )
        self.assertEqual(get_client_ip(request), PUBLIC_IP)

    @override_settings(NUM_PROXIES=3)
    def test_short_forwarded_chain_uses_leftmost(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR=f"{PUBLIC_IP}, 10.0.0.1", REMOTE_ADDR="10.0.0.2"
        )
        self.assertEqual(get_client_ip(request), PUBLIC_IP)

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get("/", REMOTE_ADDR=PUBLIC_IP)
        self.assertEqual(get_client_ip(request), PUBLIC_IP)

    @override_settings(NUM_PROXIES=1)
    def test_strips_port_suffix(self):
        # Some proxies append the port; the inet column would reject it and
        # cost the whole snapshot row.
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR=f"{PUBLIC_IP}:5678")
        self.assertEqual(get_client_ip(request), PUBLIC_IP)
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="[2001:db8::1]:443")
        self.assertEqual(get_client_ip(request), "2001:db8::1")

    @override_settings(NUM_PROXIES=1)
    def test_junk_forwarded_value_becomes_none(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="unknown", REMOTE_ADDR=PUBLIC_IP
        )
        self.assertIsNone(get_client_ip(request))

    @override_settings(NUM_PROXIES=1)
    def test_junk_forwarded_value_still_records_snapshot(self):
        user = User.objects.create_user(username="junkxff")
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="unknown")
        record_login_snapshot(sender=None, request=request, user=user)
        snapshot = LoginSnapshot.objects.get()
        self.assertIsNone(snapshot.ip_address)


class ResolveIpLocationTests(TestCase):
    def test_no_token_skips_lookup(self):
        with mock.patch("apps.users.geo.httpx.get") as get:
            self.assertEqual(resolve_ip_location(PUBLIC_IP), {})
        get.assert_not_called()

    @override_settings(IPINFO_API_TOKEN="test-token")
    def test_private_ip_skips_lookup(self):
        with mock.patch("apps.users.geo.httpx.get") as get:
            self.assertEqual(resolve_ip_location("127.0.0.1"), {})
            self.assertEqual(resolve_ip_location("192.168.1.5"), {})
            self.assertEqual(resolve_ip_location("not-an-ip"), {})
            self.assertEqual(resolve_ip_location(None), {})
        get.assert_not_called()

    @override_settings(IPINFO_API_TOKEN="test-token")
    def test_maps_response_fields(self):
        payload = {"country": "UA", "region": "Kyiv City", "city": "Kyiv"}
        with mock.patch("apps.users.geo.httpx.get", return_value=_geo_response(payload)) as get:
            result = resolve_ip_location(PUBLIC_IP)
        self.assertEqual(result, {"country_code": "UA", "region": "Kyiv City", "city": "Kyiv"})
        # Token must travel in a header - httpx embeds the request URL
        # (query string included) in exception text that gets logged.
        self.assertEqual(
            get.call_args.kwargs["headers"], {"Authorization": "Bearer test-token"}
        )

    @override_settings(IPINFO_API_TOKEN="test-token")
    def test_lookup_failure_returns_empty(self):
        import httpx

        with mock.patch("apps.users.geo.httpx.get", side_effect=httpx.ConnectError("boom")):
            self.assertEqual(resolve_ip_location(PUBLIC_IP), {})
