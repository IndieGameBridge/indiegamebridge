"""Cloudflare Turnstile server-side verification.

The frontend renders a Turnstile widget and submits the resulting token with
the contact form. We verify that token here against Cloudflare's siteverify
endpoint before accepting the submission.

If TURNSTILE_SECRET_KEY is unset (local dev), verification is skipped so the
form works without configuring Cloudflare.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        # Not configured (dev): treat as passing so the form is usable locally.
        return True

    if not token:
        return False

    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        response = httpx.post(_SITEVERIFY_URL, data=data, timeout=10)
        response.raise_for_status()
        return bool(response.json().get("success"))
    except (httpx.HTTPError, ValueError) as exc:
        # Network/parse failure verifying the token - fail closed.
        logger.warning("Turnstile verification failed: %s", exc)
        return False
