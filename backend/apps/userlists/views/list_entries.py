"""Add streamers to one of the owner's lists: one at a time, or every result of a search."""

from django.db import transaction
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.streams.models import StreamerProfile
from apps.streams.search import MAX_RESULTS, StreamerSearch
from apps.userlists.models import StreamerInList, UserListOfStreamers
from apps.userlists.views.lists import BULK_BATCH_SIZE

# As many as one saved search can hold, so adding to a list never makes it
# bigger than the largest list a search could have started.
MAX_STREAMERS_PER_LIST = MAX_RESULTS


@method_decorator(csrf_protect, name="dispatch")
class ListEntriesView(APIView):
    """POST adds streamers to the end of the owner's list.

    The body names one streamer, {"profile_id": id}, as a result row or a
    profile page does, or a whole search, {"search": "<query string>"}, re-run
    here the way saving a search as a new list re-runs it.

    Streamers already in the list are skipped, so adding one twice is harmless,
    and the answer says how many were new. An add that would take the list past
    MAX_STREAMERS_PER_LIST is refused whole rather than cut short, since which
    results made it in would be arbitrary. Another user's list is a 404, the
    same as a missing one.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "userlists_write"

    def get_throttles(self):
        # One streamer is a light write. A search is re-run and can write
        # MAX_RESULTS rows, so it spends the budget saving a new list does.
        if "search" in self.request.data:
            return [UserRateThrottle(), ScopedRateThrottle()]
        return [UserRateThrottle()]

    def post(self, request, list_id):
        profile_ids, error = self._profile_ids_to_add(request.data)
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Locked, so two adds to one list can't both pass the size check or
            # both count the same streamer as new.
            list_of_streamers = get_object_or_404(
                UserListOfStreamers.objects.select_for_update(), id=list_id, owner=request.user,
            )
            # Anonymized entries come back as None: they count towards the size
            # but match no streamer.
            in_list = list(list_of_streamers.entries.values_list("streamer_profile_id", flat=True))
            already_in = set(in_list)
            new_ids = [profile_id for profile_id in profile_ids if profile_id not in already_in]

            streamers_count = len(in_list) + len(new_ids)
            if streamers_count > MAX_STREAMERS_PER_LIST:
                return Response(
                    {"detail": f"A list holds at most {MAX_STREAMERS_PER_LIST:,} streamers,"
                        f" and this would bring it to {streamers_count:,}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # One statement per batch, in the order given, so a search's results
            # follow the existing entries ranked the way the search showed them.
            StreamerInList.objects.bulk_create(
                [
                    StreamerInList(list_of_streamers=list_of_streamers, streamer_profile_id=profile_id)
                    for profile_id in new_ids
                ],
                batch_size=BULK_BATCH_SIZE,
            )

        return Response({
            "added": len(new_ids),
            "already_in_list": len(profile_ids) - len(new_ids),
            "streamers_count": streamers_count,
        })

    @staticmethod
    def _profile_ids_to_add(data) -> tuple[list[int], dict | None]:
        """The streamers a request asks to add, in order, or the 400 payload saying what's wrong."""
        if ("profile_id" in data) == ("search" in data):
            return [], {"detail": "Send either a streamer or a search."}

        if "search" in data:
            raw_search = data["search"]
            if not isinstance(raw_search, str):
                return [], {"search": "Expected the search's query string."}
            return StreamerSearch.from_query_params(QueryDict(raw_search)).profile_ids(), None

        profile_id = data["profile_id"]
        # bool is an int subclass, and True would otherwise resolve to id 1.
        if isinstance(profile_id, bool) or not isinstance(profile_id, int):
            return [], {"profile_id": "Expected a streamer id."}
        # Gone once the streamer opted out, possibly after the page was rendered.
        if not StreamerProfile.objects.filter(id=profile_id).exists():
            return [], {"profile_id": "This streamer is no longer available."}
        return [profile_id], None
