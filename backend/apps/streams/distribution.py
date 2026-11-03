import logging

from django.utils import timezone

from apps.streams.languages import LANGUAGE_NAMES, PAGE_LANGUAGES, collected_since, day_month_year
from apps.streams.management.commands.rebuild_search_stats import WINDOW_DAYS
from apps.streams.models import JsonCache, StreamerSearchStats

logger = logging.getLogger(__name__)


DISTRIBUTION_CACHE_KEY = "streamers_distribution"

# Mirrors StreamerSearch._get_viewers_filter_values() so each bar maps 1:1 to a
# selectable "max viewers" value in the search form. Each threshold is an inclusive
# upper bound (matching the search filter's max_viewers__lte), so a streamer whose
# peak equals a threshold falls in that threshold's bucket. The last bucket catches
# everything strictly above the final threshold.
PEAK_BUCKET_THRESHOLDS = [5, 10, 15, 20, 30, 40, 50, 75, 100, 200]

# Effective floor for a stream's peak max_viewers: per HomePageBuilder's
# methodology text, streams below this many viewers don't get approved.
# Used purely for labeling the first bucket as e.g. "3-5" rather than "<5".
MIN_PEAK = 3


class StreamersDistribution:
    """Global per-streamer peak-viewer distribution over the last 4 weeks.

    Takes no input parameters: produces a single payload meant as a hint about where
    streamers cluster on the viewer-count axis. Cached in the generic streams.JsonCache
    table under DISTRIBUTION_CACHE_KEY. The cache is refreshed only by the
    refresh_distribution management command (cron) - never lazily on read - so a page
    request never triggers the recompute. results() just returns the cached payload
    (or None until the command has built it).
    """

    def results(self) -> dict | None:
        cached = JsonCache.objects.filter(key=DISTRIBUTION_CACHE_KEY).first()
        return cached.content if cached else None

    @classmethod
    def refresh(cls) -> dict:
        payload = cls.compute_payload()
        JsonCache.objects.update_or_create(
            key=DISTRIBUTION_CACHE_KEY,
            defaults={"content": payload},
        )
        return payload

    @classmethod
    def compute_payload(cls) -> dict:
        # Read straight from the precomputed search stats: each row is already a
        # (streamer, language) peak over the last 4 weeks, so the distribution
        # matches search exactly and avoids re-aggregating the wide streams table.
        # A multi-language streamer has one row per language, as search surfaces them.
        # The languages are the ones the search form offers.
        peaks_per_language = (
            StreamerSearchStats.objects
            .filter(language__in=PAGE_LANGUAGES)
            .values_list("language", "peak_viewers")
            .iterator(chunk_size=10000)
        )

        counts_by_language = {lang: [0] * (len(PEAK_BUCKET_THRESHOLDS) + 1) for lang in PAGE_LANGUAGES}
        for language, peak in peaks_per_language:
            bucket_counts = counts_by_language[language]
            for index, threshold in enumerate(PEAK_BUCKET_THRESHOLDS):
                if peak <= threshold:
                    bucket_counts[index] += 1
                    break
            else:
                bucket_counts[-1] += 1

        today = timezone.now().date()
        return {
            "title": "Streamer Peak-Viewer Distribution",
            "description": "Streamers grouped by their peak viewer count over the last 4 weeks, one row per"
                " broadcast language. Each column is the share of that language's streamers whose peak falls in"
                " the range, so the languages compare despite very different totals; each row names its total."
                " Use it as a hint when choosing the 'Max Viewers' range in the search form.",
            # The rows in page order, with their names: the buckets' keys don't keep an
            # order, since JSONB sorts them.
            "languages": [cls._language(language, today) for language in PAGE_LANGUAGES],
            "buckets": {
                language: cls._build_buckets(counts_by_language[language])
                for language in PAGE_LANGUAGES
            },
        }

    @staticmethod
    def _language(language: str, today) -> dict:
        since = collected_since(language, today, WINDOW_DAYS)
        return {
            "code": language,
            "label": LANGUAGE_NAMES[language],
            # A row whose 4 weeks haven't filled yet says so.
            "note": f"Collected since {day_month_year(since)}" if since else None,
        }

    @staticmethod
    def _build_buckets(bucket_counts: list[int]) -> list[dict]:
        buckets = []
        for index, threshold in enumerate(PEAK_BUCKET_THRESHOLDS):
            lower = MIN_PEAK if index == 0 else PEAK_BUCKET_THRESHOLDS[index - 1] + 1
            buckets.append({"x": f"{lower}-{threshold}", "y": bucket_counts[index]})
        buckets.append({"x": f"{PEAK_BUCKET_THRESHOLDS[-1] + 1}+", "y": bucket_counts[-1]})
        return buckets
