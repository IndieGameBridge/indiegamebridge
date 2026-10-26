from .add_to_list import add_to_list_labels
from .base import BaseCachedPageBuilder


class StreamerProfilePageBuilder(BaseCachedPageBuilder):
    key = "streamer_profile"
    log_label = "Streamer profile page"

    def build_content(self) -> dict:
        return {
            "title": f"Streamer: %streamer_display_name%",
            "add_to_list": add_to_list_labels(),
            "stats_title": f"Last 4-Week Stats",
            "streams_title": f"All Streams",
            "show_more": f"Show More",
            "notes": [
                f"Streams with smaller, more variable audiences shift positions in Twitch's results between our polls,"
                    f" which is the main reason for 'no data' gaps."
                    f" Larger streams with stable viewer counts hold their position and get captured more consistently.",
            ],
        }
