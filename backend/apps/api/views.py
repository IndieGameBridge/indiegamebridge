from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pages.models import CachedPage
from apps.streams.search import StreamerSearch
from apps.pages.cached_pages import HomePageBuilder


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

        header = page_parts.get("page_header")
        footer = page_parts.get("page_footer")
        page.content["header_content"] = header.content if header else None
        page.content["footer_content"] = footer.content if footer else None

        if key == HomePageBuilder.key:
            filters_config, _ = StreamerSearch.get_filters_config()
            page.content["search_form"]["filters"] = filters_config
            page.content["search_results"] = StreamerSearch().results()

        return Response(page.content)


class StreamerSearchView(APIView):
    """Run a streamer search.

    Query params mirror the form field names. Multi-valued params (e.g. genre,
    week_days) can be repeated: ?week_days=1&week_days=5. Missing params fall
    back to StreamerSearch.default_filters().
    """

    # Multi-valued query params — read via getlist so repeated keys are preserved.
    # Names must match the filter config in StreamerSearch.get_filters_config.
    _LIST_PARAMS = ("wdays",)

    def get(self, request):
        raw_filters = {}
        for key in request.GET.keys():
            if key in self._LIST_PARAMS:
                raw_filters[key] = request.GET.getlist(key)
            else:
                raw_filters[key] = request.GET.get(key)

        search = StreamerSearch(raw_filters)
        return Response({
            "filters": search.filters,
            "results": search.results(),
        })
