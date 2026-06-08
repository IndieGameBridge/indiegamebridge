from django.db import connection
from django.db.models import Max

from .base import BaseCachedPageBuilder
from apps.streams.models import Stream, StreamerProfile, StreamerSearchStats
from apps.streams.search import StreamerSearch


class HomePageBuilder(BaseCachedPageBuilder):
    key = "home"
    log_label = "Home page"

    def build_content(self) -> dict:
        # Approximate, O(1) headline counts: MAX(id) for streamers (profiles are
        # only removed on opt-out, so it tracks the total seen) and the planner's
        # row estimate for streams. Avoids COUNT scans over the streams table that
        # grow with the data.
        total_streamers = StreamerProfile.objects.aggregate(max_id=Max("id"))["max_id"] or 0
        total_streams = self._estimated_stream_count()
        # Searchable streamers = rows in the precomputed search table (active in the
        # last 4 weeks). Slightly over the distinct count since a multi-language
        # streamer has one row per language, but that's a tiny fraction - and the
        # figure is presented as approximate anyway. Cheap COUNT on a ~1M narrow table.
        searchable_streamers = StreamerSearchStats.objects.count()
        filters_config, _ = StreamerSearch.get_filters_config()

        return {
            "title": f"IndieGameBridge",
            "description": f"Find Twitch streamers worth pitching your indie game to",
            "info": f"Tracking {self._approx(total_streamers)} streamers across {self._approx(total_streams)} observed streams,"
                f" with {self._approx(searchable_streamers)} active and searchable in the last 4 weeks",
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
                    "Results are based on each streamer's streams from the last 4 weeks."
                ],
                "demo_note": f"The search form is a demo of the real search form, which is available for logged in users."
                    f" The results below are real, matching the search parameters prefilled in the form and updated daily.",
                "cta_link_text": f"Log in to use the search"
            },
            "search_results": StreamerSearch().results(limit=50),
            "results_labels": {
                "view_profile": f"View Profile",
                "show_more": f"Show More",
                "loading": f"Loading...",
            },
        }

    @staticmethod
    def _estimated_stream_count() -> int:
        # Planner row estimate (instant) instead of an exact COUNT that scans the
        # whole streams table. Non-approved streams are a small transient slice,
        # so the whole-table estimate closely tracks the approved count.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = %s",
                [Stream._meta.db_table],
            )
            row = cursor.fetchone()
        estimate = int(row[0]) if row and row[0] else 0
        if estimate > 0:
            return estimate
        # Fallback if the table was never ANALYZEd (reltuples = -1): exact count.
        return Stream.objects.filter(status=Stream.Status.APPROVED).count()

    @staticmethod
    def _approx(value: int) -> str:
        # Deliberately approximate display, e.g. 2,538,318 -> "2.5M".
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.0f}K"
        return str(value)
