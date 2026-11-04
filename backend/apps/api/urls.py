from django.urls import path

from apps.api.views import (
    CachedPageContentView,
    GameHoursView,
    GameSearchView,
    StreamerSearchView,
    StreamersDistributionView,
)


urlpatterns = [
    path("pages/<slug:key>/", CachedPageContentView.as_view(), name="cached-page-content"),
    path("streamers/", StreamerSearchView.as_view(), name="streamer-search"),
    path("streamers/distribution/", StreamersDistributionView.as_view(), name="streamers-distribution"),
    path("games/", GameSearchView.as_view(), name="game-search"),
    path("games/<int:game_id>/hours/", GameHoursView.as_view(), name="game-hours"),
]
