"""The owner's lists of streamers: read them for the dashboard, or save a search as a new one."""

from django.http import QueryDict
from django.db import transaction
from django.db.models import Count
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.streams.search import StreamerSearch
from apps.userlists.models import (
    StreamerInList,
    UserLabelForListOfStreamers,
    UserListOfStreamers,
)

# How many lists one user may keep. A product limit, not a safety one - see the
# note on the race in post().
MAX_LISTS_PER_USER = 20

# Mirror the model's column limits so oversized input is rejected as a 400 here
# rather than blowing up at the Postgres column boundary as a 500.
MAX_TITLE = 32
MAX_DESCRIPTION = 512

# Rows are written in one statement, but 5,000 of them is a lot to hold in memory
# as model instances at once.
BULK_BATCH_SIZE = 1000


def _clean(value) -> str:
    """Trim, and strip the NUL bytes Postgres text columns reject."""
    return str(value or "").replace("\x00", "").strip()


@method_decorator(csrf_protect, name="dispatch")
class ListsView(APIView):
    """The signed-in user's lists of streamers.

    GET returns all of them, newest first, for the dashboard's cards. POST saves
    the streamers matching a search as a new list.

    POST carries the search's query string rather than thousands of ids: the ids
    would not fit in a URL, and re-running the search server-side keeps one
    definition of what the filters mean. The trade is that the stats table
    rebuilds roughly daily, so a list saved long after the page was rendered can
    differ from it by a row or two.
    """

    permission_classes = [IsAuthenticated]
    # Tighter than the global per-user ceiling, and spent by POST only: one call
    # re-runs the search and writes up to MAX_RESULTS rows, making it the
    # heaviest write in the app.
    throttle_scope = "userlists_write"

    def get_throttles(self):
        # Reads stay on the global ceiling, so loading the dashboard never counts
        # against saving a list.
        if self.request.method == "POST":
            return [UserRateThrottle(), ScopedRateThrottle()]
        return [UserRateThrottle()]

    def get(self, request):
        lists_of_streamers = (
            UserListOfStreamers.objects.filter(owner=request.user)
            .annotate(streamers_count=Count("entries"))
            .prefetch_related("labels")
            # Django ignores Meta.ordering once annotate() adds a GROUP BY, so
            # without this the cards would come back in no fixed order.
            .order_by(*UserListOfStreamers._meta.ordering)
        )
        return Response({
            "lists": [
                {
                    "id": one_list.id,
                    "title": one_list.title,
                    "description": one_list.description,
                    "labels": [
                        {"id": label.id, "title": label.title, "color": label.color}
                        for label in one_list.labels.all()
                    ],
                    # Anonymized entries count too: the list still holds them,
                    # notes and all.
                    "streamers_count": one_list.streamers_count,
                    "created_at": one_list.created_at.isoformat(),
                }
                for one_list in lists_of_streamers
            ],
        })

    def post(self, request):
        title = _clean(request.data.get("title"))
        if not title:
            return self._bad_request({"title": "Give the list a title."})
        if len(title) > MAX_TITLE:
            return self._bad_request({"title": f"At most {MAX_TITLE} characters."})

        description = _clean(request.data.get("description"))
        if len(description) > MAX_DESCRIPTION:
            return self._bad_request(
                {"description": f"At most {MAX_DESCRIPTION} characters."}
            )

        labels, label_error = self._resolve_labels(request)
        if label_error:
            return self._bad_request(label_error)

        # Not a lock: two simultaneous requests could both pass this and leave the
        # user with 21 lists. The cap is there to keep the dashboard manageable,
        # so a rare overshoot costs nothing that locking every create would repay.
        if UserListOfStreamers.objects.filter(owner=request.user).count() >= MAX_LISTS_PER_USER:
            return self._bad_request(
                {"detail": f"You already have the maximum of {MAX_LISTS_PER_USER} lists."}
            )

        search = StreamerSearch.from_query_params(QueryDict(request.data.get("search") or ""))
        profile_ids = search.profile_ids()

        with transaction.atomic():
            list_of_streamers = UserListOfStreamers.objects.create(
                owner=request.user, title=title, description=description,
            )
            if labels:
                list_of_streamers.labels.set(labels)
            StreamerInList.objects.bulk_create(
                [
                    StreamerInList(
                        list_of_streamers=list_of_streamers, streamer_profile_id=profile_id,
                    )
                    for profile_id in profile_ids
                ],
                batch_size=BULK_BATCH_SIZE,
            )

        return Response(
            {
                "id": list_of_streamers.id,
                "title": list_of_streamers.title,
                "streamers_count": len(profile_ids),
            },
            status=status.HTTP_201_CREATED,
        )

    def _resolve_labels(self, request) -> tuple[list, dict | None]:
        """The owner's labels for the given ids, or an error describing what's wrong.

        A label belonging to someone else and a label that doesn't exist get the
        same answer, so this can't be used to probe for other users' label ids.
        """
        raw = request.data.get("labels") or []
        if not isinstance(raw, list):
            return [], {"labels": "Expected a list of label ids."}

        label_ids = set()
        for one_raw in raw:
            # bool is an int subclass, and True would otherwise resolve to id 1.
            if isinstance(one_raw, bool) or not isinstance(one_raw, int):
                return [], {"labels": "Expected a list of label ids."}
            label_ids.add(one_raw)

        if not label_ids:
            return [], None

        labels = list(
            UserLabelForListOfStreamers.objects.filter(owner=request.user, id__in=label_ids)
        )
        if len(labels) != len(label_ids):
            return [], {"labels": "Unknown label."}
        return labels, None

    @staticmethod
    def _bad_request(payload: dict) -> Response:
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)
