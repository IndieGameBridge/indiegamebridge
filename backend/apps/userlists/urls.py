from django.urls import path

from apps.userlists.views import ListsView


urlpatterns = [
    path("lists/", ListsView.as_view(), name="userlists-lists"),
]
