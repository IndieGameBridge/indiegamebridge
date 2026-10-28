from django.urls import path

from apps.exports.views import ListExportView, SearchExportView


urlpatterns = [
    path(
        "lists/<int:list_id>/export/<slug:file_format>/",
        ListExportView.as_view(),
        name="exports-list",
    ),
    path(
        "streamers/export/<slug:file_format>/",
        SearchExportView.as_view(),
        name="exports-search",
    ),
]
