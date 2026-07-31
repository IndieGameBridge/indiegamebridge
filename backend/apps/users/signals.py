"""Login bookkeeping: store a LoginSnapshot on every successful login.

Hooks django.contrib.auth's user_logged_in signal, which fires both for the
Twitch OAuth flow (allauth calls django login() before the finalize view mints
JWT cookies) and for password logins to the Django admin.

All of it is gated on AccountSettings.allow_tracking ("Allow feature-usage
tracking" in the frontend settings page): when the user has disabled tracking,
neither a snapshot nor a last_login update is recorded. Django's built-in
update_last_login receiver is disconnected in UsersConfig.ready() and called
conditionally from here instead - it is the only way to make last_login
respect the toggle.
"""

import ipaddress
import logging

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.users.geo import resolve_ip_location
from apps.users.models import AccountSettings, LoginSnapshot

logger = logging.getLogger(__name__)


def _clean_ip(raw: str | None) -> str | None:
    """Normalize a forwarded address to a bare IP, or None if it isn't one.

    Some proxies write X-Forwarded-For entries with a port ("1.2.3.4:5678",
    "[2001:db8::1]:443"); the model's inet column rejects those, which would
    silently cost the whole snapshot row.
    """
    if not raw:
        return None
    candidate = raw.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass
    host = candidate.rsplit(":", 1)[0].strip("[]")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def get_client_ip(request) -> str | None:
    """Client IP using the same NUM_PROXIES logic as DRF's throttling.

    With proxies in front (Next.js = 1), take the NUM_PROXIES-th address from
    the right of X-Forwarded-For - entries further left are client-forgeable.

    Same trust caveat as the throttling config (see NUM_PROXIES in settings):
    a request that reaches the Django origin directly can forge the header,
    so the recorded IP is best-effort telemetry, not a security audit trail -
    which fits its purpose, since users can switch the whole snapshot off via
    the tracking toggle anyway.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    num_proxies = settings.NUM_PROXIES
    if forwarded and num_proxies > 0:
        addrs = [addr.strip() for addr in forwarded.split(",")]
        return _clean_ip(addrs[-min(num_proxies, len(addrs))])
    return _clean_ip(request.META.get("REMOTE_ADDR"))


def _tracking_allowed(user) -> bool:
    """The AccountSettings row is created lazily, so a missing row means the
    user never touched the toggle - that's the model default (True)."""
    allowed = (
        AccountSettings.objects.filter(user=user)
        .values_list("allow_tracking", flat=True)
        .first()
    )
    return True if allowed is None else allowed


@receiver(user_logged_in)
def record_login_snapshot(sender, request, user, **kwargs):
    try:
        if not _tracking_allowed(user):
            return
        update_last_login(sender, user, **kwargs)
        ip = get_client_ip(request) if request is not None else None
        location = resolve_ip_location(ip)
        LoginSnapshot.objects.create(user=user, ip_address=ip, **location)
    except Exception:
        # Telemetry only - never let snapshot bookkeeping break a login.
        logger.exception("Failed to record login snapshot for %s", user)
