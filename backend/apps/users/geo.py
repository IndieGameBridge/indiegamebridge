"""IP -> coarse location lookup via ipinfo.io.

If IPINFO_API_TOKEN is unset (the default), lookups are skipped entirely and
login snapshots record only user/time/IP. ipinfo.io is used rather than a
Google API because Google Maps has no endpoint for locating an *arbitrary* IP
(its Geolocation API only locates the caller); ipinfo's free tier returns
country code, region and city, which is all a login snapshot needs.
"""

import ipaddress
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_LOOKUP_URL = "https://ipinfo.io/{ip}/json"


def resolve_ip_location(ip: str | None) -> dict:
    """Return {"country_code", "region", "city"} for a public IP, else {}.

    Never raises: location is best-effort enrichment and must not be able to
    break a login. Private/loopback addresses (local dev) are skipped without
    an HTTP call.
    """
    token = settings.IPINFO_API_TOKEN
    if not token or not ip:
        return {}

    try:
        if not ipaddress.ip_address(ip).is_global:
            return {}
    except ValueError:
        return {}

    try:
        # Token goes in a header, not the query string: httpx error messages
        # embed the full request URL, and those get logged below. Short
        # timeout - this runs inline in the login request path.
        response = httpx.get(
            _LOOKUP_URL.format(ip=ip),
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "country_code": (data.get("country") or "")[:2],
            "region": (data.get("region") or "")[:100],
            "city": (data.get("city") or "")[:100],
        }
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("IP location lookup failed for %s: %s", ip, exc)
        return {}
