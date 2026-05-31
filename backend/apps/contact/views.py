"""Public contact-form submission endpoint."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.contact.models import ContactMessage
from apps.contact.turnstile import verify_turnstile

# Mirror the model's column limits so we reject oversized input early.
# Without these, oversized input passes validation and only fails at the
# Postgres column boundary - an unhandled 500 instead of a clean 400.
_MAX_NAME = 120
_MAX_EMAIL = 254
_MAX_SUBJECT = 200
_MAX_MESSAGE = 5000

# Field a real browser leaves empty; bots that fill every input trip it.
_HONEYPOT_FIELD = "company"


def _clean(value) -> str:
    """Coerce to a trimmed string and strip NUL bytes.

    Postgres text columns reject NUL (0x00); removing it here turns a would-be
    500 on insert into ordinary input handling. Whitespace is trimmed so
    blank-but-spaces input is treated as empty.
    """
    return str(value).replace("\x00", "").strip()


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class ContactMessageView(APIView):
    """Accept an anonymous contact submission and store it for admin review.

    Unauthenticated by design, so there's no CSRF requirement (no ambient
    credentials to abuse). Abuse is handled by three layers: a honeypot field,
    a per-IP rate limit, and Cloudflare Turnstile verification.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "contact"

    def post(self, request):
        data = request.data

        # Honeypot: accept-and-drop so a bot can't tell it was filtered.
        if str(data.get(_HONEYPOT_FIELD, "")).strip():
            return Response(status=status.HTTP_201_CREATED)

        if not verify_turnstile(str(data.get("turnstile_token", "")), _client_ip(request)):
            return Response(
                {"detail": "Verification failed. Please complete the challenge and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = _clean(data.get("name", ""))
        email = _clean(data.get("email", ""))
        subject = _clean(data.get("subject", ""))
        message = _clean(data.get("message", ""))

        errors = {}
        if not name:
            errors["name"] = "This field is required."
        elif len(name) > _MAX_NAME:
            errors["name"] = "This field is too long."

        if not email:
            errors["email"] = "This field is required."
        elif len(email) > _MAX_EMAIL:
            errors["email"] = "This field is too long."
        else:
            try:
                validate_email(email)
            except ValidationError:
                errors["email"] = "Enter a valid email address."

        if not message:
            errors["message"] = "This field is required."
        elif len(message) > _MAX_MESSAGE:
            errors["message"] = "This field is too long."

        if len(subject) > _MAX_SUBJECT:
            errors["subject"] = "This field is too long."

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        ContactMessage.objects.create(
            name=name,
            email=email,
            subject=subject,
            message=message,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
        )
        return Response(status=status.HTTP_201_CREATED)
