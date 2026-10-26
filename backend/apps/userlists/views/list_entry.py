"""One streamer in one of the owner's lists: write the owner's note on them, or remove them."""

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.userlists.models import StreamerInList
from apps.userlists.views.lists import _clean

# Mirrors StreamerInList.description, so an oversized note is a 400 here rather
# than a 500 at the column boundary.
MAX_NOTE = 512


@method_decorator(csrf_protect, name="dispatch")
class ListEntryView(APIView):
    """One entry of the owner's list. PATCH replaces its note; an empty one clears
    it. DELETE removes the streamer from the list, note and all.

    The entry is looked up through its list's owner, so another user's entry is a
    404, the same as a missing one. Both are light writes, so they stay on the
    global per-user throttle rather than spending the list-creation budget.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, list_id, entry_id):
        entry = self._get_entry(request, list_id, entry_id)

        description = _clean(request.data.get("description"))
        if len(description) > MAX_NOTE:
            return Response(
                {"description": f"At most {MAX_NOTE} characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entry.description = description
        entry.save(update_fields=["description"])
        return Response({"id": entry.id, "description": entry.description})

    def delete(self, request, list_id, entry_id):
        # Adding the streamer again puts them at the end, with no note.
        self._get_entry(request, list_id, entry_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _get_entry(request, list_id, entry_id) -> StreamerInList:
        return get_object_or_404(
            StreamerInList,
            id=entry_id,
            list_of_streamers_id=list_id,
            list_of_streamers__owner=request.user,
        )
