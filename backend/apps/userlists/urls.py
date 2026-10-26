from django.urls import path

from apps.userlists.views import ListDetailView, ListEntriesView, ListEntryView, ListsView


urlpatterns = [
    path("lists/", ListsView.as_view(), name="userlists-lists"),
    path("lists/<int:list_id>/", ListDetailView.as_view(), name="userlists-list"),
    path("lists/<int:list_id>/entries/", ListEntriesView.as_view(), name="userlists-entries"),
    path(
        "lists/<int:list_id>/entries/<int:entry_id>/",
        ListEntryView.as_view(),
        name="userlists-entry",
    ),
]
