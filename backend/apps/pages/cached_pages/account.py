from .base import BaseCachedPageBuilder


class AccountPageBuilder(BaseCachedPageBuilder):
    key = "account"
    log_label = "Account settings page"

    def build_content(self) -> dict:
        return {
            "title": f"Account Settings",
            "body": f"Account settings are coming soon. You will be able to manage your profile and preferences here.",
        }
