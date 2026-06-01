"""Auth-related view - Stream Exclusion toggle (authenticated PATCH).

Lets a logged-in user exclude their Twitch ID from streams collection (opt out)
or re-include it (opt in) from the Account Settings page, WITHOUT ending their
session. The standalone OptOutView remains the logout-style flow used by the
public opt-out page.
"""

from allauth.socialaccount.models import SocialAccount
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import TwitchExclusion
from apps.users.views.opt_in import perform_opt_in
from apps.users.views.opt_out import perform_opt_out


@method_decorator(csrf_protect, name="dispatch")
class StreamExclusionView(APIView):
    """Toggle the current user's Twitch streams exclusion. PATCH with
    {"excluded": bool}; the session is left intact either way. Returns the
    resulting exclusion state (False if no Twitch account is linked)."""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        excluded = request.data.get("excluded")
        if not isinstance(excluded, bool):
            return Response(
                {"excluded": "Expected a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if excluded:
            perform_opt_out(request.user)
        else:
            perform_opt_in(request.user)

        social = SocialAccount.objects.filter(user=request.user, provider="twitch").first()
        is_excluded = bool(social) and TwitchExclusion.objects.filter(twitch_id=social.uid).exists()
        return Response({"excluded": is_excluded})
