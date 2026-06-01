from django.urls import path

from apps.api.views import CachedPageContentView, StreamerSearchView, StreamersDistributionView


urlpatterns = [
    path("pages/<slug:key>/", CachedPageContentView.as_view(), name="cached-page-content"),
    path("streamers/", StreamerSearchView.as_view(), name="streamer-search"),
    path("streamers/distribution/", StreamersDistributionView.as_view(), name="streamers-distribution"),
]
