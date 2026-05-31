from django.urls import path

from apps.users.views import (
    AccountSettingsView,
    CurrentUserView,
    LogoutView,
    OAuthFinalizeView,
    OptOutView,
    RefreshCookieView,
    StreamExclusionView,
)


urlpatterns = [
    path("currentuser/", CurrentUserView.as_view(), name="auth-current-user"),
    path("settings/", AccountSettingsView.as_view(), name="auth-account-settings"),
    path("stream-exclusion/", StreamExclusionView.as_view(), name="auth-stream-exclusion"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("optout/", OptOutView.as_view(), name="auth-opt-out"),
    path("token/refresh/", RefreshCookieView.as_view(), name="auth-token-refresh"),
    path("finalize-login/", OAuthFinalizeView.as_view(), name="auth-finalize-login"),
]
