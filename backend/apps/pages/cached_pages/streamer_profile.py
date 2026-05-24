from .base import BaseCachedPageBuilder


class StreamerProfilePageBuilder(BaseCachedPageBuilder):
    key = "streamer_profile"
    log_label = "Streamer profile page"

    def build_content(self) -> dict:
        return {
            "title": f"Streamer: %streamer_display_name%",
            "body": f"Detailed streamer profile is coming soon. The data source and caching strategy are still being decided.",
        }
