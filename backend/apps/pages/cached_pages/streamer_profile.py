from .base import BaseCachedPageBuilder


class StreamerProfilePageBuilder(BaseCachedPageBuilder):
    key = "streamer_profile"
    log_label = "Streamer profile page"

    def build_content(self) -> dict:
        return {
            "title": f"Streamer: %streamer_display_name%",
            "explain": f"NOTE: Streams with smaller, more variable audiences shift positions in Twitch's results between our polls,"
                " which is the main reason for 'no data' gaps."
                " Larger streams with stable viewer counts hold their position and get captured more consistently.",
        }
