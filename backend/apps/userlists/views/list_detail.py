"""One of the owner's lists of streamers: read it a page at a time, edit it, or delete it."""

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.streams.search import PAGE_SIZE, StreamerSearch
from apps.userlists.models import UserListOfStreamers
from apps.userlists.views.lists import clean_description, clean_title


@method_decorator(csrf_protect, name="dispatch")
class ListDetailView(APIView):
    """One list and a page of its entries, in the order they were saved.

    Each entry carries the streamer's current stats in the list's language - the
    one its search ran in - so the list reads like the results it came from, with
    live numbers. A list made by hand has no such language, so each of its
    streamers shows in their main one instead.

    PATCH edits the title and note, DELETE removes the list with its entries.
    Both are light writes, left on the global per-user throttle. Another user's
    list is a 404, the same as a missing one.
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
        profile_ids = [entry.streamer_profile_id for entry in entries if entry.streamer_profile_id]

        # Empty for a list made by hand: no search to describe, and no search
        # language to show stats in.
        search = (
            StreamerSearch(list_of_streamers.search_filters)
            if list_of_streamers.search_filters
            else None
        )
        stats = (
            StreamerSearch.stats_for_profiles(profile_ids, search.filters["lang"])
            if search
            else StreamerSearch.main_language_stats_for_profiles(profile_ids)
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
            # Whether the list came from a search, which only those can re-run.
            "from_search": search is not None,
            "search": search.describe() if search else [],
            "entries": [self._entry(entry, stats) for entry in entries],
        })

    def patch(self, request, list_id):
        list_of_streamers = get_object_or_404(UserListOfStreamers, id=list_id, owner=request.user)

        # Only the fields sent change, so one can be edited without resending the other.
        update_fields = []
        if "title" in request.data:
            title, error = clean_title(request.data)
            if error:
                return Response(error, status=status.HTTP_400_BAD_REQUEST)
            list_of_streamers.title = title
            update_fields.append("title")
        if "description" in request.data:
            description, error = clean_description(request.data)
            if error:
                return Response(error, status=status.HTTP_400_BAD_REQUEST)
            list_of_streamers.description = description
            update_fields.append("description")

        if update_fields:
            # auto_now only applies to fields named in update_fields.
            list_of_streamers.save(update_fields=[*update_fields, "updated_at"])
        return Response({
            "id": list_of_streamers.id,
            "title": list_of_streamers.title,
            "description": list_of_streamers.description,
        })

    def delete(self, request, list_id):
        # Entries and label links go with it; the labels themselves stay.
        get_object_or_404(UserListOfStreamers, id=list_id, owner=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
                # None when they have no recent streams in the list's language,
                # or for a list made by hand, none at all.
                "stats": stats.get(profile.id),
            },
        }
