from .base import BaseCachedPageBuilder


class AccountPageBuilder(BaseCachedPageBuilder):
    key = "account"
    log_label = "Account settings page"

    def build_content(self) -> dict:
        return {
            "title": f"Account Settings",
            "tracking_label": f"Allow feature-usage tracking for service improvement",
            "exclusion_label": f"Allow streams tracking for my Twitch ID",
            "exclusion_warning": f"Turning this off removes all data tied to your Twitch ID and excludes it from future collection."
                f" The removed data cannot be restored, though you can turn tracking back on anytime to re-enable future collection."
                f" The public page and search results may still show your data for up to an hour while caches refresh.",
            "exclusion_confirm": f"This removes all data tied to your Twitch ID and excludes it from future collection."
                f" The removed data cannot be restored. Continue?",
            "danger_zone": {
                "title": f"Danger zone",
                "description": f"Permanently delete your account and account settings. This cannot be undone."
                    f" Your Twitch streams data is only removed if you tick the option below.",
                "optout_label": f"Also stop collecting and delete my Twitch streams data",
                "delete_confirm": f"This permanently deletes your account and cannot be undone. Continue?",
                "delete_btn": f"Delete account",
            },
        }
