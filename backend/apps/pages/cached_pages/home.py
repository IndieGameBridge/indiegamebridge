from .base import BaseCachedPageBuilder
from apps.streams.models import Stream, StreamerProfile
from apps.streams.search import StreamerSearch


class HomePageBuilder(BaseCachedPageBuilder):
    key = "home"
    log_label = "Home page"

    def build_content(self) -> dict:
        total_streamers = StreamerProfile.objects.filter(streams__status=Stream.Status.APPROVED).distinct().count()
        total_streams = Stream.objects.filter(status=Stream.Status.APPROVED).count()

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
            "search_form": {
                "title": "Search Streamers",
                "aria_label": "Demonstration search form",
                "filters": [],
                "btn_text": "Apply Filters",
                "demo_title": f"Note:",
                "search_notes": [
                    "Times are in UTC. Days of week and the time window are both based on when each stream went offline. A UTC day can straddle two local days in non-UTC zones."
                ],
                "demo_note": f"The search form is a demo of the real search form, which is available for logged in users."
                    f" The results below are real, matching the search parameters prefilled in the form and updating hourly.",
                "cta_link_text": f"Log in to use the search"
            },
            "search_results": [],
            "search_results_title": "Search Results",
            "roadmap": {
                "title": f"What's Coming",
                "description": f"The project is in active development."
                    f" Planned features include:",
                "features": [
                    f"Developer profile with extra features.",
                    f"Streamer profile with extra features.",
                    # Possible next features:
                    #   'Developer profile' with extra features:
                    #       - Create a favorites list of streamers - pick selected streamers from the search results and save them to a stored list
                    #           (useful for narrowing a larger result set down to the ones worth following up on).
                    #       - Add notes to streamers in the favorites list - e.g. whether and when the developer contacted the streamer, and what the streamer
                    #           replied or whether they ignored the message. Communication itself is assumed to happen outside the platform for now, but these notes
                    #           help organize the search results.
                    #       - Mark streamers in the favorites list with different colors to visually distinguish them - helps with organization.
                    #       - Sort streamers in the favorites list - reorder entries manually.
                    #       - Per-list notes and custom names for each favorites list - makes it easier to navigate between multiple lists.
                    #       - Store up to N past search results - lets the user revisit previous searches and compare them with newer ones
                    #           (maybe also a 'compare tool' to find streamers appearing in two or more search results).
                    # MAYBE LATER:
                    #   'Streamer profile' - lets streamers be discovered by developers interested in collaboration; streamers can voluntarily
                    #       leave a message and contact info. Likely needs manual moderation, AI moderation, or both.
                    #   'Public developer profile' - for developers who want to use the platform as an additional promotion channel
                    #       for their game(s). Likely needs manual moderation, AI moderation, or both.
                    #   Features to make communication easier on both sides (the idea is to offer a dedicated place for communication without forcing anyone
                    #   to use the platform if they prefer other channels):
                    #       - direct messages
                    #       - built-in Zoom-style calls and meetings
                    #       - ratings and statistics
                    #       - integrated promo codes (to make collaboration more automated and reduce overhead for both sides)
                    #       - AI best-match search (a quick-start option for users who don't want to spend time on a thorough search or want to reduce overhead)
                ]
            },
            "methodology": {
                "title": f"Methodology",
                "description": f"We poll live Twitch streams every 20 minutes via the Helix API."
                    f" Each snapshot records the game, viewer count, date, and time."
                    f" Once a stream ends, we compute its peak viewer count from the snapshots collected while it was live,"
                    f" and if any snapshot recorded at least 3 viewers, we add the stream to the streamer's statistics.",
            },
        }
