from .base import BaseCachedPageBuilder
from apps.streams.models import Stream, StreamerProfile
from apps.streams.search import StreamerSearch


class HomePageBuilder(BaseCachedPageBuilder):
    key = "home"
    log_label = "Home page"

    def build_content(self) -> dict:
        total_streamers = StreamerProfile.objects.filter(streams__status=Stream.Status.APPROVED).distinct().count()
        total_streams = Stream.objects.filter(status=Stream.Status.APPROVED).count()
        filters_config, _ = StreamerSearch.get_filters_config()

        return {
            "title": f"IndieGameBridge",
            "description": f"Find Twitch streamers worth pitching your indie game to",
            "info": f"Currently tracking {total_streamers:,} streamers across {total_streams:,} observed streams",
            "project_goal": {
                "title": f"What this project is for",
                "description": f"The project aims to help indie developers find and collaborate with streamers who regularly broadcast specific game genres to a relevant audience."
                    f" The platform only aggregates statistics from publicly available information provided by Twitch via the Helix API."
                    f" We do not collect or share any private information.",
            },
            "methodology": {
                "title": f"Methodology",
                "description": f"We poll live Twitch streams every 20 minutes via the Helix API."
                    f" Each snapshot records the game, viewer count, date, and time."
                    f" Once a stream ends, we compute its peak viewer count from the snapshots collected while it was live,"
                    f" and if any snapshot recorded at least 3 viewers, we add the stream to the streamer's statistics.",
            },
            "search_form": {
                "title": "Search Streamers",
                "aria_label": "Demonstration search form",
                "filters": filters_config,
                "btn_text": "Apply Filters",
                "demo_title": f"Note:",
                "search_notes": [
                    "Times are in UTC. Days of week and the time window are both based on when each stream went offline. A UTC day can straddle two local days in non-UTC zones."
                ],
                "demo_note": f"The search form is a demo of the real search form, which is available for logged in users."
                    f" The results below are real, matching the search parameters prefilled in the form and updating hourly.",
                "cta_link_text": f"Log in to use the search"
            },
            "search_results": StreamerSearch().results(limit=50),
            "results_labels": {
                "view_profile": f"View Profile",
                "show_more": f"Show More",
                "loading": f"Loading...",
            },
        }
