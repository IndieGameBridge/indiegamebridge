"""Download a list or a search as a file: Excel, CSV or JSON."""

import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import content_disposition_header, urlencode
from django.utils.text import slugify
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.exports.files import FILE_TYPES, About
from apps.exports.models import Export
from apps.exports.rows import LIST_COLUMNS, STREAMER_COLUMNS, list_rows, search_rows
from apps.streams.search import StreamerSearch
from apps.userlists.models import UserListOfStreamers
from apps.users.models import AccountSettings

logger = logging.getLogger(__name__)


class ExportView(APIView):
    """What both exports share: signed-in users only, on an hourly budget of their own.

    The format comes as a path segment rather than ?format=, because DRF reads
    that query param as a pick of one of its own renderers and answers 404 when
    none matches.
    """

    permission_classes = [IsAuthenticated]
    # On top of the global per-user ceiling: one export reads up to MAX_RESULTS
    # streamers. Nobody exporting by hand gets near the limit; it's there so a
    # script can't page through the data a file at a time.
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "exports"

    @staticmethod
    def check_file_format(file_format):
        """Before any query: a format there's no writer for is a 404."""
        if file_format not in FILE_TYPES:
            raise Http404

    def file_response(self, file_format, rows, columns, about: About, name: str, **record) -> HttpResponse:
        content_type, write = FILE_TYPES[file_format]
        response = HttpResponse(write(rows, columns, about), content_type=content_type)
        filename = f"indiegamebridge-{name}-{about.exported_at:%Y-%m-%d}.{file_format}"
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
        # One user's own data: no shared cache may keep a copy.
        add_never_cache_headers(response)
        self._record(file_format=file_format, rows=len(rows), **record)
        return response

    def _record(self, **fields):
        """Feature-usage tracking, so only for users who allow it, and never at the cost of the file."""
        user = self.request.user
        try:
            if AccountSettings.tracking_allowed(user):
                Export.objects.create(user=user, **fields)
        except Exception:
            logger.exception("Failed to record an export for %s", user)


class ListExportView(ExportView):
    """One of the user's lists, every entry, with the stats and notes its page shows.

    Another user's list is a 404, the same as a missing one.
    """

    def get(self, request, list_id, file_format):
        self.check_file_format(file_format)
        list_of_streamers = get_object_or_404(UserListOfStreamers, id=list_id, owner=request.user)
        rows = list_rows(list_of_streamers)
        search = (
            StreamerSearch(list_of_streamers.search_filters).describe()
            if list_of_streamers.search_filters
            else []
        )
        about = About(
            source=Export.Source.LIST,
            url=f"{settings.FRONTEND_URL}/lists/{list_of_streamers.id}",
            exported_at=timezone.now(),
            title=list_of_streamers.title,
            search=search,
            removed_streamers=sum(1 for row in rows if row["twitch_login"] is None),
        )
        return self.file_response(
            file_format, rows, LIST_COLUMNS, about,
            name=slugify(list_of_streamers.title, allow_unicode=True) or "list",
            source=Export.Source.LIST,
            list_of_streamers=list_of_streamers,
        )


class SearchExportView(ExportView):
    """Every streamer a search finds - the same ones saving it as a list would keep.

    The search arrives as the results page's own query string.
    """

    def get(self, request, file_format):
        self.check_file_format(file_format)
        search = StreamerSearch.from_query_params(request.GET)
        explicit_filters = search.explicit_filters()
        about = About(
            source=Export.Source.SEARCH,
            # Every filter spelled out, so the link re-runs this search even
            # after the form's defaults change.
            url=f"{settings.FRONTEND_URL}/streamers?{urlencode(explicit_filters, doseq=True)}",
            exported_at=timezone.now(),
            search=search.describe(),
        )
        return self.file_response(
            file_format, search_rows(search), STREAMER_COLUMNS, about,
            name=f"search-{search.filters['lang']}",
            source=Export.Source.SEARCH,
            search_filters=explicit_filters,
        )
