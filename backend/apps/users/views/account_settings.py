"""Auth-related view - Account Settings (authenticated update)."""

from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import AccountSettings


@method_decorator(csrf_protect, name="dispatch")
class AccountSettingsView(APIView):
    """Update the current user's account-wide settings. PATCH with any subset
    of the known fields; the settings row is created lazily on first access."""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        account_settings, _ = AccountSettings.objects.get_or_create(user=request.user)

        allow_tracking = request.data.get("allow_tracking")
        if allow_tracking is not None:
            if not isinstance(allow_tracking, bool):
                return Response(
                    {"allow_tracking": "Expected a boolean."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            account_settings.allow_tracking = allow_tracking
            account_settings.save(update_fields=["allow_tracking"])

        return Response({"allow_tracking": account_settings.allow_tracking})
