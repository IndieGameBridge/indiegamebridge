from django.urls import path

from apps.contact.views import ContactMessageView


urlpatterns = [
    path("contact/", ContactMessageView.as_view(), name="contact-message"),
]
