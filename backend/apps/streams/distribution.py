import logging
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from apps.streams.models import JsonCache, Stream

logger = logging.getLogger(__name__)


DISTRIBUTION_CACHE_KEY = "streamers_distribution"
DISTRIBUTION_CACHE_TTL = timedelta(hours=24)
DISTRIBUTION_WINDOW_DAYS = 28

# Mirrors StreamerSearch._get_viewers_filter_values() so each bar maps 1:1 to a
# selectable "max viewers" value in the search form. Last bucket catches everything
# at or above the final threshold.
PEAK_BUCKET_THRESHOLDS = [5, 10, 15, 20, 30, 40, 50, 75, 100, 200, 300, 400, 500, 750, 1000, 2000, 3000, 4000, 5000, 10000, 50000, 100000]

# Mirrors the language filter in StreamerSearch. Hardcoded in both places for now;
# expected to move to admin-managed settings once the polling language list becomes
# configurable.
LANGUAGES = ["en", "fr", "de"]


class StreamersDistribution:
    """Global per-streamer peak-viewer distribution over the last DISTRIBUTION_WINDOW_DAYS.

    Takes no input parameters: produces a single payload meant as a hint about where
    streamers cluster on the viewer-count axis. Cached in the generic streams.JsonCache
    table under DISTRIBUTION_CACHE_KEY with a 24h TTL-on-read; results() self-heals on
    miss/stale so the endpoint stays useful without a separate pre-warm job.
    """

    def results(self) -> dict:
        now = timezone.now()
        cached = JsonCache.objects.filter(key=DISTRIBUTION_CACHE_KEY).first()

        if cached and (now - cached.updated_at) < DISTRIBUTION_CACHE_TTL:
            logger.debug("Distribution cache hit")
            return cached.content

        logger.debug("Distribution cache %s", "stale" if cached else "miss")
        return self.refresh()

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
        window_start = timezone.now() - timedelta(days=DISTRIBUTION_WINDOW_DAYS)

        # Per-(streamer, language) peak. A streamer who streams in multiple languages
        # contributes one row per language, matching how the search would surface them
        # under each lang filter.
        peaks_per_language = (
            Stream.objects
            .filter(
                status=Stream.Status.APPROVED,
                finished_at__gte=window_start,
                language__in=LANGUAGES,
            )
            .values("streamer_profile_id", "language")
            .annotate(peak=Max("max_viewers"))
            .values_list("language", "peak")
        )

        counts_by_language = {lang: [0] * (len(PEAK_BUCKET_THRESHOLDS) + 1) for lang in LANGUAGES}
        for language, peak in peaks_per_language:
            bucket_counts = counts_by_language[language]
            for index, threshold in enumerate(PEAK_BUCKET_THRESHOLDS):
                if peak < threshold:
                    bucket_counts[index] += 1
                    break
            else:
                bucket_counts[-1] += 1

        return {
            "window_days": DISTRIBUTION_WINDOW_DAYS,
            "buckets": {
                language: cls._build_buckets(counts_by_language[language])
                for language in LANGUAGES
            },
        }

    @staticmethod
    def _build_buckets(bucket_counts: list[int]) -> list[dict]:
        buckets = [
            {"x": f"<{threshold}", "y": bucket_counts[index]}
            for index, threshold in enumerate(PEAK_BUCKET_THRESHOLDS)
        ]
        buckets.append({"x": f"{PEAK_BUCKET_THRESHOLDS[-1]}+", "y": bucket_counts[-1]})
        return buckets
