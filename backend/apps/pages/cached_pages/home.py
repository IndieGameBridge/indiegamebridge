from datetime import timedelta

from django.contrib.postgres.aggregates import JSONBAgg
from django.db.models import Max, F
from django.db.models.functions import ExtractIsoWeekDay, JSONObject
from django.utils import timezone

from .base import BaseCachedPageBuilder
from apps.streams.models import Game, GameGenre, Stream, StreamerProfile
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
            "search_form": self._get_search_form(),
            "search_results_title": "Search Results",
            "search_results": self._get_demo_search_results(),
            "roadmap": {
                "title": f"What's Coming",
                "description": f"The project is in active development."
                    f" Planned features include:",
                "features": [
                    f"Export search results in your preferred file format.",
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

    def _format_duration(self, duration=0):
        hours, r = divmod(duration, 3600)
        minutes, r = divmod(r, 60)
        return f"{hours} h " + f"{minutes} min"

    def _get_demo_search_results(self) -> tuple[list[dict]]:
        # TODO: use StreamerSearch class instead
        # Hardcoded filter values for the demo. The real search will expose these via the form.
        demo_language = "en"
        demo_window_start = timezone.now() - timedelta(days=14)
        demo_wdays = [1, 5, 6, 7]
        demo_durmin = 1800
        demo_durmax = 36000
        demo_peakmin = 100
        demo_peakmax = 100000
        demo_genres = [5]

        # Aggregate top streamers from the filtered stream set.
        top_streamer_aggregates = list(
            Stream.objects.filter(
                status=Stream.Status.APPROVED,
                finished_at__gte=demo_window_start,
                language=demo_language,
                duration__gte=demo_durmin,
                duration__lte=demo_durmax,
                max_viewers__gte=demo_peakmin,
                max_viewers__lte=demo_peakmax,
                genre_ids__overlap=demo_genres
            )
            .annotate(
                finished_dow=ExtractIsoWeekDay("finished_at")
            )
            .filter(
                finished_dow__in=demo_wdays
            )
            .annotate(
                host_login=F("streamer_profile__host_login"),
                host_display_name=F("streamer_profile__host_display_name")
            )
            .values(
                login=F("host_login"),
                display_name=F("host_display_name"),
                profile_id=F("streamer_profile_id")
            )
            .annotate(
                peak_viewers=Max("max_viewers"),
                streams=JSONBAgg(
                    JSONObject(
                        id="id",
                        duration="duration",
                        max_viewers="max_viewers",
                        language="language",
                        game_ids="host_game_ids",
                        started_at="started_at",
                        finished_at="finished_at"
                    )
                )
            )
            .order_by("-peak_viewers")[: 10]
        )

        # Resolve every referenced game in a single query.
        all_game_ids = {
            one_game_id
            for one_streamer in top_streamer_aggregates
            for one_stream in one_streamer.get("streams", [])
            for one_game_id in one_stream.get("game_ids", [])
        }

        game_names_map = dict(
            Game.objects.filter(host_game_id__in=all_game_ids)
            .values_list("host_game_id", "host_name")
        )

        # Replace game_ids with human-readable game names and format the duration.
        for one_streamer in top_streamer_aggregates:
            for stream in one_streamer.get("streams", []):
                stream["games"] = [
                    game_names_map.get(game_id, "N/A")
                    for game_id in (stream.get("game_ids") or [])
                ]
                stream["duration"] = self._format_duration(duration=stream["duration"])
                stream.pop("game_ids", None)

        return top_streamer_aggregates

    @staticmethod
    def _get_search_form():
        filters_config, _ = StreamerSearch.get_filters_config()
        return {
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
        }
