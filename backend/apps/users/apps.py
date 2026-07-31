from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    label = "users"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from apps.users import signals  # noqa: F401

        # last_login is gated on AccountSettings.allow_tracking: replace
        # Django's unconditional receiver with the conditional call inside
        # record_login_snapshot (apps.users.signals). auth's ready() runs
        # before ours (INSTALLED_APPS order), so the receiver exists here.
        user_logged_in.disconnect(dispatch_uid="update_last_login")
