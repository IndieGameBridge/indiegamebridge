from .base import BaseCachedPageBuilder


class LoginPageBuilder(BaseCachedPageBuilder):
    key = "login"
    log_label = "Login page"

    def build_content(self) -> dict:
        return {
            "title": f"Log in",
            "prompt": f"IndieGameBridge uses your Twitch account to verify you. We never see your password.",
            "twitch_login_btn": f"Log in with Twitch",
            "more_options_note": f"More login options coming later.",
        }
