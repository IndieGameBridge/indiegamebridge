"""Auth-related view - Delete Account (authenticated)."""

from django.db import transaction
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.cookies import clear_jwt_cookies
from apps.users.views.opt_out import perform_opt_out


@method_decorator(csrf_protect, name="dispatch")
class DeleteAccountView(APIView):
    """Permanently delete the authenticated user's account, then clear cookies.

    With {"opt_out": true} it also opts the Twitch ID out (excludes it and
    deletes collected streams data) before the account is removed.

    Deleting the User cascades to AccountSettings, the allauth SocialAccount,
    and the user's JWT token records. Any token still held by the client fails
    auth afterwards because the user no longer exists, so no separate blacklist
    step is needed.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        opt_out = bool(request.data.get("opt_out"))

        with transaction.atomic():
            if opt_out:
                # Resolves the Twitch ID via the SocialAccount, so it must run
                # before the user (and its SocialAccount) is deleted.
                perform_opt_out(user)
            user.delete()

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_jwt_cookies(response)
        return response
