from django.http import Http404
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.pages.models import CachedPage
from apps.streams.distribution import StreamersDistribution
from apps.streams.models import StreamerProfile
from apps.streams.profile import StreamerProfileStreams
from apps.streams.search import PAGE_SIZE as SEARCH_PAGE_SIZE, StreamerSearch


class CachedPageContentView(APIView):
    """Public read-only endpoint that returns the JSON payload of a cached page by key."""

    def get(self, request, key):
        page_parts = {
            p.key: p
            for p in CachedPage.objects.filter(key__in=[key, "page_header", "page_footer"])
        }
        page = page_parts.get(key)
        if page is None:
            raise Http404
        
        if key == "streamer_profile":
            twitch_login = request.GET.get("twitch_login", "")
            streamer_profile = (
                StreamerProfile.objects
                .filter(host=StreamerProfile.Host.TWITCH, host_login=twitch_login)
                .first()
            )
            page.content["title"] = page.content["title"].replace(
                "%streamer_display_name%",
                streamer_profile.host_display_name if streamer_profile else "Not found",
            )
            payload = StreamerProfileStreams(streamer_profile).results() if streamer_profile else {"streams": [], "stats": None}
            page.content["streams"] = payload["streams"]
            page.content["stats"] = payload["stats"]

        header = page_parts.get("page_header")
        footer = page_parts.get("page_footer")
        page.content["header_content"] = header.content if header else None
        page.content["footer_content"] = footer.content if footer else None

        return Response(page.content)


class StreamerSearchView(APIView):
    """Run a streamer search.

    Query params mirror the form field names. Multi-valued params (e.g. genre,
    week_days) can be repeated: ?week_days=1&week_days=5. Missing params fall
    back to StreamerSearch.default_filters().
    """

    # Stricter per-IP cap (the "search" rate) on top of the global anon/user
    # ceiling, since each search runs a fresh filtered Postgres query. Listing
    # throttle_classes here replaces the project defaults, so the global
    # classes are re-included alongside the scoped one.
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    # Multi-valued query params — read via getlist so repeated keys are preserved.
    # Names must match the filter config in StreamerSearch.get_filters_config.
    _LIST_PARAMS = ("wdays",)

    # Query params that control paging rather than filtering — excluded from the
    # filter dict so they don't affect the cache key.
    _PAGING_PARAMS = ("p",)

    def get(self, request):
        raw_filters = {}
        for key in request.GET.keys():
            if key in self._PAGING_PARAMS:
                continue
            if key in self._LIST_PARAMS:
                raw_filters[key] = request.GET.getlist(key)
            else:
                raw_filters[key] = request.GET.get(key)

        try:
            page = max(1, int(request.GET.get("p", "1")))
        except ValueError:
            page = 1
        offset = (page - 1) * SEARCH_PAGE_SIZE

        search = StreamerSearch(raw_filters)
        return Response({
            "filters": search.filters,
            "results": search.results(offset=offset, limit=SEARCH_PAGE_SIZE),
            "total": search.total(),
        })


class StreamersDistributionView(APIView):
    """Public read-only endpoint returning the cached global peak-viewer distribution."""

    def get(self, request):
        return Response(StreamersDistribution().results())
