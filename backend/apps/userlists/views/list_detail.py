"""One of the owner's lists of streamers, with its entries a page at a time."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.streams.search import PAGE_SIZE, StreamerSearch
from apps.userlists.models import UserListOfStreamers


class ListDetailView(APIView):
    """One list and a page of its entries, in the order they were saved.

    Each entry carries the streamer's current stats in the list's language - the
    one its search ran in - so the list reads like the results it came from, with
    live numbers. Another user's list is a 404, the same as a missing one.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, list_id):
        list_of_streamers = get_object_or_404(
            UserListOfStreamers.objects.prefetch_related("labels"),
            id=list_id,
            owner=request.user,
        )

        try:
            page = max(1, int(request.GET.get("p", "1")))
        except ValueError:
            page = 1
        offset = (page - 1) * PAGE_SIZE
        entries = list(
            list_of_streamers.entries.select_related("streamer_profile")[offset:offset + PAGE_SIZE]
        )

        # Empty for a list created by hand: no search language to show stats in,
        # and nothing to describe.
        search = (
            StreamerSearch(list_of_streamers.search_filters)
            if list_of_streamers.search_filters
            else None
        )
        stats = (
            StreamerSearch.stats_for_profiles(
                [entry.streamer_profile_id for entry in entries if entry.streamer_profile_id],
                search.filters["lang"],
            )
            if search
            else {}
        )

        return Response({
            "id": list_of_streamers.id,
            "title": list_of_streamers.title,
            "description": list_of_streamers.description,
            "labels": [
                {"id": label.id, "title": label.title, "color": label.color}
                for label in list_of_streamers.labels.all()
            ],
            "created_at": list_of_streamers.created_at.isoformat(),
            "streamers_count": list_of_streamers.entries.count(),
            "search": search.describe() if search else [],
            "entries": [self._entry(entry, stats) for entry in entries],
        })

    @staticmethod
    def _entry(entry, stats: dict) -> dict:
        profile = entry.streamer_profile
        return {
            "id": entry.id,
            "description": entry.description,
            "added_at": entry.added_at.isoformat(),
            # None once the streamer opted out; the page shows the entry anonymized.
            "streamer": None if profile is None else {
                "login": profile.host_login,
                "display_name": profile.host_display_name,
                # None when they have no recent streams in the list's language.
                "stats": stats.get(profile.id),
            },
        }
