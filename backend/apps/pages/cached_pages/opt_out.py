from .base import BaseCachedPageBuilder


class OptOutPageBuilder(BaseCachedPageBuilder):
    key = "optout"
    log_label = "Opt-out page"

    def build_content(self) -> dict:
        return {
            "title": f"Opt Out",
            "return_home": f"Return to Home Page",
            "not_logged_in": {
                "prompt": f"Want to opt out? Click below to log in with your Twitch account so we can verify your Twitch ID. We will then remove all data tied to it and exclude it from future collection.",
                "login_btn": f"Log in with Twitch to verify your Twitch ID",
            },
            "logged_in": {
                "prompt": f"Want to opt out? Click below to confirm. All data tied to your Twitch ID will be removed automatically and excluded from future collection. The removed data cannot be restored, but you can opt back in anytime from your account settings to re-enable future data collection. Your data may still appear on public pages for up to an hour due to cache latency.",
                "optout_btn": f"Opt Out",
            },
            "already_optout": f"You have already opted out, and we have handled it. We no longer collect or store any data about your streams. You can opt back in anytime from your account settings to re-enable future data collection.",
            "success_optout": f"We have verified your Twitch ID and removed all data tied to it. Going forward, we will exclude it from future collection. The removed data cannot be restored, but you can opt back in anytime from your account settings to re-enable future collection. The public page may still show your data for up to an hour while caches refresh.",
        }
