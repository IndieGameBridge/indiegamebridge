from datetime import date, timedelta

from django.db.models import Max
from django.utils import timezone

from .base import BaseCachedPageBuilder
from apps.streams.languages import LANGUAGE_NAMES, PAGE_LANGUAGES, collected_since, day_month_year, names_of
from apps.streams.management.commands.rebuild_genre_stats import WINDOW_DAYS
from apps.streams.models import GameGenre, GenreStats


class GenreTrendsPageBuilder(BaseCachedPageBuilder):
    """Public Genre Trends pages: three per-genre diagrams over the last 4 weeks.

    Reads the precomputed GenreStats rows (built by rebuild_genre_stats) and shapes
    them into chart-ready payloads. Each genre's bar carries one value per broadcast
    language. The overview page, /genre-trends, adds the languages up; each language
    has a page of its own, /genre-trends/<slug>, with its own copy in `language_pages`,
    so each can be found by searches for that language. Every defined genre is shown,
    including zero-value ones, so a page also tells the 'this genre was never popular'
    story.
    """

    key = "genre_trends"
    log_label = "Genre Trends page"

    def build_content(self) -> dict:
        genre_names = list(
            GameGenre.objects.values_list("host_name", flat=True)
        )
        rows = list(
            GenreStats.objects
            .select_related("genre")
            .filter(language__in=PAGE_LANGUAGES)
            .values_list(
                "genre__host_name",
                "language",
                "streams_count",
                "streamers_count",
                "total_duration_seconds",
            )
        )
        computed_at = GenreStats.objects.aggregate(latest=Max("computed_at"))["latest"]
        today = timezone.now().date()
        languages = [{"code": code, "label": LANGUAGE_NAMES[code]} for code in PAGE_LANGUAGES]
        all_names = names_of(PAGE_LANGUAGES)

        return {
            "title": "Genre Trends",
            "description": "How Twitch game genres compare by real streaming activity over the last 4 weeks.",
            # SEO <title> / meta description, kept separate from the visible
            # header above (which doubles as the page's h1/intro).
            "seo_title": "Twitch Game Genre Trends & Streaming Stats | IndieGameBridge",
            "seo_description": "Compare Twitch game genres by real streaming activity: streams, streamers and hours per"
                f" genre over the last 4 weeks, overall and in {len(PAGE_LANGUAGES)} broadcast languages.",
            "intro": "Wondering which game genres are most popular on Twitch right now? The charts below rank every"
                " genre we track by real streaming activity over the last 4 weeks - not just viewer counts, but how many"
                " streams happened, how many distinct streamers took part, and how many hours they broadcast. They add up"
                f" the broadcast languages we track - {all_names} - and each language has a page of its own, so you can"
                " see where a genre's audience actually is. For indie game developers, that shows where an engaged"
                " streamer audience already exists for games like yours, and which genres are worth focusing your"
                " outreach on. The data is rebuilt daily from live Twitch streams.",
            "note": self._overview_note(today),
            # The 4 weeks the numbers cover, for the pages' structured data.
            "window": {
                "start": (computed_at - timedelta(days=WINDOW_DAYS)).date().isoformat(),
                "end": computed_at.date().isoformat(),
                "computed_at": computed_at.isoformat(),
            } if computed_at else None,
            "language_pages": [self._language_page(code, today) for code in PAGE_LANGUAGES],
            # Grants nothing, on purpose: Twitch's developer agreement forbids licensing data built
            # from its API without its written permission. The pages' structured data points here.
            "data_use": "The numbers on this page are for reading here. They come from Twitch's API and IGDB, so"
                " IndieGameBridge can't license them for reuse, and no license is given. Linking to this page is"
                " welcome.",
            "faq": {
                "title": "Frequently asked questions",
                "items": [
                    {
                        "question": "Which game genres are most streamed on Twitch?",
                        "answer": "The charts above rank genres by number of streams, distinct streamers, and hours"
                            " broadcast over the last 4 weeks. The leading genres shift over time, so the data is"
                            " recomputed daily from live Twitch streams rather than fixed all-time totals.",
                    },
                    {
                        "question": "How is genre streaming activity measured?",
                        "answer": "We poll live Twitch streams every 20 minutes via the official Helix API and record the"
                            " game, viewer count, and time of each snapshot. Each stream's time is split across the genres"
                            " it actually played, and non-game time such as Just Chatting is excluded.",
                    },
                    {
                        "question": "How often is the genre data updated?",
                        "answer": "Genre trends are recomputed daily and always cover a rolling 4-week window, so they"
                            " reflect current streaming activity rather than all-time totals.",
                    },
                    {
                        "question": "Which languages are included in the genre trends?",
                        "answer": f"The {len(PAGE_LANGUAGES)} broadcast languages we track: {all_names}. This page"
                            " adds them up, and each language has a page of its own with its own ranking. Streams in"
                            " other languages aren't counted.",
                    },
                    {
                        "question": "How can indie developers use genre trends?",
                        "answer": "A genre with many active streamers and hours streamed is one where an engaged audience"
                            " already exists. Indie developers can use these trends to focus outreach on the genres - and"
                            " the streamers - that best match their game.",
                    },
                ],
            },
            "diagrams": [
                {
                    "title": "Streams per genre",
                    "description": "Number of streams in the last 4 weeks that played at least one game of"
                        " each genre. A stream spanning several genres counts toward each.",
                    "y_label": "Streams",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=2),
                },
                {
                    "title": "Streamers per genre",
                    "description": "Distinct streamers who broadcast at least one game of each genre in the"
                        " last 4 weeks.",
                    # Only where the languages are added up: each language counts its own
                    # distinct streamers, so the sum counts a few twice (about 0.2%).
                    "overview_note": "Added up across languages, a streamer who streams in two languages counts"
                        " once in each.",
                    "y_label": "Streamers",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=3),
                },
                {
                    "title": "Hours streamed per genre",
                    "description": "Total hours broadcast per genre in the last 4 weeks. Each stream's time is"
                        " split across the genres it actually played; non-game time (e.g. Just Chatting) is"
                        " excluded.",
                    "y_label": "Hours",
                    "languages": languages,
                    "bars": self._bars(genre_names, rows, value_index=4, to_hours=True),
                },
            ],
        }

    @staticmethod
    def _language_page(code: str, today: date) -> dict:
        label = LANGUAGE_NAMES[code]
        since = collected_since(code, today, WINDOW_DAYS)
        return {
            "code": code,
            # The page's URL: /genre-trends/japanese.
            "slug": label.lower(),
            "label": label,
            "title": f"Genre Trends in {label}",
            "description": f"How Twitch game genres compare in {label}-language streams over the last 4 weeks.",
            "seo_title": f"Twitch Game Genre Trends in {label} | IndieGameBridge",
            "seo_description": f"Which game genres {label}-language Twitch streamers play most: streams, streamers"
                " and hours per genre over the last 4 weeks, rebuilt daily from live streams.",
            "intro": f"Which game genres are most popular with {label}-language streamers on Twitch? The charts below"
                " rank every genre we track by how many streams played it, how many distinct streamers took part,"
                f" and how many hours they broadcast in {label} over the last 4 weeks. For indie game developers,"
                f" that shows where an engaged {label}-speaking streamer audience already exists for games like"
                " yours. The data is rebuilt daily from live Twitch streams.",
            "note": (
                f"{label} streams have been collected since {day_month_year(since)}, so these numbers cover"
                f" {_days(today - since)} so far, not 4 weeks."
            ) if since else None,
        }

    @staticmethod
    def _overview_note(today: date) -> str | None:
        # The languages whose 4 weeks haven't filled yet, grouped by when collecting began.
        partial = {}
        for code in PAGE_LANGUAGES:
            since = collected_since(code, today, WINDOW_DAYS)
            if since is not None:
                partial.setdefault(since, []).append(code)
        sentences = [
            f"{names_of(codes)} streams have been collected since {day_month_year(since)}, so their part of"
            f" these numbers covers {_days(today - since)} so far, not 4 weeks."
            for since, codes in sorted(partial.items())
        ]
        return " ".join(sentences) or None

    @staticmethod
    def _bars(genre_names, rows, value_index: int, to_hours: bool = False) -> list[dict]:
        # One bar per genre, each carrying a per-language value map. Seed every defined
        # genre with zeros for all languages so genres with no activity still render
        # (and every bar has the full language set the legend expects).
        by_genre = {name: {code: 0 for code in PAGE_LANGUAGES} for name in genre_names}
        for row in rows:
            name, language = row[0], row[1]
            if name not in by_genre or language not in by_genre[name]:
                continue
            value = row[value_index]
            if to_hours:
                value = round(value / 3600)
            by_genre[name][language] = value

        bars = [{"x": name, "values": values} for name, values in by_genre.items()]
        bars.sort(key=lambda bar: sum(bar["values"].values()), reverse=True)
        return bars


def _days(span: timedelta) -> str:
    if span.days == 0:
        return "less than a day"
    return "1 day" if span.days == 1 else f"{span.days} days"
