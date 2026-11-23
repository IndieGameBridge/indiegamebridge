from django.urls import path

from apps.api.views import (
    CachedPageContentView,
    GameHoursView,
    GamePagesView,
    GamePageView,
    GameSearchView,
    StreamerLookupView,
    StreamerSearchView,
    StreamersDistributionView,
)


urlpatterns = [
    path("pages/<slug:key>/", CachedPageContentView.as_view(), name="cached-page-content"),
    path("streamers/", StreamerSearchView.as_view(), name="streamer-search"),
    path("streamers/distribution/", StreamersDistributionView.as_view(), name="streamers-distribution"),
    # Called from the browser, which reaches the backend only under /api/ (the frontend's proxy).
    path("api/streamers/find/", StreamerLookupView.as_view(), name="streamer-lookup"),
    path("games/", GameSearchView.as_view(), name="game-search"),
    path("games/<int:game_id>/hours/", GameHoursView.as_view(), name="game-hours"),
    path("games/pages/", GamePagesView.as_view(), name="game-pages"),
    path("games/pages/<slug:slug>/", GamePageView.as_view(), name="game-page"),
]
