from django.urls import path

from apps.api.views import CachedPageContentView, StreamerSearchView


urlpatterns = [
    path("pages/<slug:key>/", CachedPageContentView.as_view(), name="cached-page-content"),
    path("streamers/search/", StreamerSearchView.as_view(), name="streamer-search"),
]
