from .base import BaseCachedPageBuilder
from apps.streams.models import Stream, StreamerProfile


class PageHeaderBuilder(BaseCachedPageBuilder):
    key = "page_header"
    log_label = "Page header"

    def build_content(self) -> dict:
        total_streamers = StreamerProfile.objects.filter(streams__status=Stream.Status.APPROVED).distinct().count()
        total_streams = Stream.objects.filter(status=Stream.Status.APPROVED).count()

        return {
            "title": f"IndieGameBridge",
            "description": f"Find Twitch streamers worth pitching your indie game to",
            "info": f"Currently tracking {total_streamers:,} streamers across {total_streams:,} observed streams",
        }
