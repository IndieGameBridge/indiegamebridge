from django.urls import path

from apps.userlists.views import CreateListView


urlpatterns = [
    path("lists/", CreateListView.as_view(), name="userlists-create"),
]
