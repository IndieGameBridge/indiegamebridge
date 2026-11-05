from datetime import date

from django.db.models import Sum
from django.utils import timezone

from .base import BaseCachedPageBuilder
from apps.streams.game_search import GameSearch
from apps.streams.languages import PAGE_LANGUAGES
from apps.streams.models import GenreStats, StreamerSearchStats
from apps.streams.search import DEFAULT_SIZE_GROUP, GENRE_FILTER_NAMES, StreamerSearch

# IGDB's id for the Indie genre. The page's samples keep to it, since the plain top of the
# Games list is Fortnite and the like, which says little to an indie developer.
INDIE_GENRE_ID = 32

# Rows in a sample.
SAMPLE_ROWS = 5


class HomePageBuilder(BaseCachedPageBuilder):
    key = "home"
    log_label = "Home page"

    def build_content(self) -> dict:
        active_streamers, recent_streams = self.search_window_counts()

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
            "info": f"Tracking {self.approx(active_streamers)} streamers active in the last 4 weeks"
                f" across {self.approx(recent_streams)} observed streams, all of them searchable",
            "project_goal": {
                "title": f"How indie developers find the right Twitch streamers",
                "description": f"IndieGameBridge helps indie game developers find and collaborate with Twitch streamers who regularly broadcast specific game genres to a relevant audience."
                    f" Instead of guessing who to pitch, you can see who plays games like yours, which games are streamed now, and which genres have an audience.",
            },
            "showcase": self._showcase(),
            "methodology": {
                "title": f"How we measure Twitch streaming activity",
                "description": f"We poll live Twitch streams every 20 minutes via the Helix API."
                    f" Each snapshot records the game, viewer count, date, and time."
                    f" Once a stream ends, we compute its peak viewer count from the snapshots collected while it was live,"
                    f" and if any snapshot recorded at least 3 viewers, we add the stream to the streamer's statistics.",
                "note": f"The platform only aggregates statistics from publicly available information provided by Twitch via the Helix API."
                    f" We do not collect or share any private information.",
            },
        }

    def _showcase(self) -> dict:
        """A block per feature: what it does, a button to it, and a small sample of real data."""
        games_year = self._games_sample_year(timezone.now().date())
        return {
            "header_buttons": {
                "streamers": "Find streamers",
                "games": "See what's streamed now",
            },
            "streamers": {
                "title": "Find the streamers worth pitching",
                "text": "Search streamers by the genres they really play, their language and how many viewers they"
                    " really get, from their streams of the last 4 weeks. So you can see who already has an audience"
                    " for games like yours.",
                "btn": "Search streamers",
                "sample_title": f"Indie streamers in English, {DEFAULT_SIZE_GROUP} max viewers",
                "columns": {"name": "Streamer", "avg": "Avg viewers", "streams": "Streams", "hours": "Hours"},
                "rows": StreamerSearch({GENRE_FILTER_NAMES[0]: INDIE_GENRE_ID}).results(limit=SAMPLE_ROWS),
            },
            "lists": {
                "title": "Keep your shortlist in lists",
                "text": "Save a whole search as a list, or add streamers one by one. Keep a private note on each"
                    " streamer, and export a list to Excel, CSV or JSON when you're ready to reach out.",
                "login_btn": "Log in to create lists",
                "open_btn": "Open your lists",
            },
            "games": {
                "title": "See which games are streamed right now",
                "text": "Open any game to see how many streams were live on it in each hour of the last 4 weeks, in"
                    " each language. The quiet hours are when a stream of it meets the fewest competitors.",
                "btn": "Explore games",
                "sample_title": f"Indie games released in {games_year}, all languages",
                # The rows themselves are read on each request: the game numbers change every
                # 6 hours, and this page is rebuilt once a day.
                "sample_query": f"{GENRE_FILTER_NAMES[0]}={INDIE_GENRE_ID}&year={games_year}",
                "columns": {"name": "Game", "hours": ["Newest hour", "1 h before", "2 h before"]},
            },
            "genres": {
                "title": "Compare genres before you pitch",
                "text": "See which game genres have the most streams, streamers and hours over the last 4 weeks,"
                    " overall and in each language, so you know where an audience for your kind of game already"
                    " exists.",
                "btn": "See genre trends",
                "sample_title": "Streams per genre, last 4 weeks, all languages",
                "rows": self._genre_rows(),
            },
        }

    @staticmethod
    def _games_sample_year(today: date) -> int:
        # A new year's list starts nearly empty, so last year's shows until it has filled.
        search = GameSearch({GENRE_FILTER_NAMES[0]: INDIE_GENRE_ID, "year": today.year})
        return today.year if "year" in search.filters and search.total() >= SAMPLE_ROWS else today.year - 1

    @staticmethod
    def _genre_rows() -> list[dict]:
        # The biggest genres by streams, and Indie wherever it stands, with its place.
        genres = list(
            GenreStats.objects
            .filter(language__in=PAGE_LANGUAGES)
            .values("genre__host_genre_id", "genre__host_name")
            .annotate(streams=Sum("streams_count"))
            .order_by("-streams", "genre__host_name")
        )
        rows = []
        for place, genre in enumerate(genres, 1):
            is_indie = genre["genre__host_genre_id"] == INDIE_GENRE_ID
            if place <= SAMPLE_ROWS or is_indie:
                name = genre["genre__host_name"]
                rows.append({
                    "name": f"{name} (#{place} of {len(genres)})" if is_indie else name,
                    "streams": genre["streams"],
                    "marked": is_indie,
                })
        return rows

    @staticmethod
    def search_window_counts() -> tuple[int, int]:
        # Streamers and streams over the search window, read from the precomputed
        # search table: the headline then describes exactly what a search can find,
        # and nothing counts over the streams table. So it counts only the languages
        # the search form offers. A streamer has a row per language, hence the
        # distinct; a stream has one language, so it's in one row.
        rows = StreamerSearchStats.objects.filter(language__in=PAGE_LANGUAGES)
        streamers = rows.values("streamer_profile_id").distinct().count()
        streams = rows.aggregate(total=Sum("streams_count"))["total"] or 0
        return streamers, streams

    @staticmethod
    def approx(value: int) -> str:
        # Deliberately approximate display, e.g. 2,538,318 -> "2.5M".
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.0f}K"
        return str(value)
