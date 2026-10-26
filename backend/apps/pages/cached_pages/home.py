from django.db.models import Sum

from .base import BaseCachedPageBuilder
from apps.streams.models import StreamerSearchStats
from apps.streams.search import StreamerSearch


class HomePageBuilder(BaseCachedPageBuilder):
    key = "home"
    log_label = "Home page"

    def build_content(self) -> dict:
        active_streamers, recent_streams = self._search_window_counts()
        filters_config, _ = StreamerSearch.get_filters_config()

        demo_search = StreamerSearch()

        return {
            "title": f"IndieGameBridge",
            "description": f"Find Twitch streamers worth pitching your indie game to",
            # SEO <title> / meta description, kept separate from the visible
            # header above. The header doubles as the page's h1/intro, so it
            # stays brand-led, while these are keyword-led for search results.
            "seo_title": "Find Twitch Streamers for Your Indie Game | IndieGameBridge",
            "seo_description": "Find Twitch streamers who actively play your game's genre, "
                "ranked by real viewership from the last 4 weeks. IndieGameBridge helps indie "
                "developers reach the right streamers to pitch and grow their audience.",
            "info": f"Tracking {self._approx(active_streamers)} streamers active in the last 4 weeks"
                f" across {self._approx(recent_streams)} observed streams, all of them searchable",
            "project_goal": {
                "title": f"How indie developers find the right Twitch streamers",
                "description": f"IndieGameBridge helps indie game developers find and collaborate with Twitch streamers who regularly broadcast specific game genres to a relevant audience."
                    f" Instead of guessing who to pitch, you can search streamers by the genres they actually play and by their recent viewership, so your outreach reaches creators whose audience already enjoys games like yours."
                    f" The platform only aggregates statistics from publicly available information provided by Twitch via the Helix API."
                    f" We do not collect or share any private information.",
            },
            "methodology": {
                "title": f"How we measure Twitch streaming activity",
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
                    "Results are based on each streamer's streams from the last 4 weeks."
                ],
                "demo_note": f"The search form is a demo of the real search form, which is available for logged in users."
                    f" The results below are real, matching the search parameters prefilled in the form and updated daily.",
                "cta_link_text": f"Log in to use the search"
            },
            "search_results": demo_search.results(limit=50),
            "search_total": demo_search.total(),
            "results_labels": {
                "found_count": "Found {count} streamers",
                "view_profile": f"View Profile",
                "show_more": f"Show More",
                "loading": f"Loading...",
            },
        }

    @staticmethod
    def _search_window_counts() -> tuple[int, int]:
        # Streamers and streams over the search window, read from the precomputed
        # search table: the headline then describes exactly what a search can find,
        # and nothing counts over the streams table. A streamer has a row per
        # language, hence the distinct; a stream has one language, so it's in one row.
        rows = StreamerSearchStats.objects
        streamers = rows.values("streamer_profile_id").distinct().count()
        streams = rows.aggregate(total=Sum("streams_count"))["total"] or 0
        return streamers, streams

    @staticmethod
    def _approx(value: int) -> str:
        # Deliberately approximate display, e.g. 2,538,318 -> "2.5M".
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.0f}K"
        return str(value)
