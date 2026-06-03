import logging
from datetime import timedelta

from django.contrib.postgres.aggregates import JSONBAgg
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Avg, Count, Max, Sum
from django.utils import timezone

from apps.streams.models import (
    SearchStatsRebuildState,
    Stream,
    StreamerProfile,
    StreamerSearchStats,
)

logger = logging.getLogger(__name__)

# Fixed search window: stats summarise each streamer's last 4 weeks.
WINDOW_DAYS = 28

DEFAULT_CHUNK = 20000


class Command(BaseCommand):
    help = (
        "Recompute the StreamerSearchStats read-model in rolling chunks. Walks"
        " StreamerProfile ids behind a saved cursor so repeated cron runs cover"
        " the whole set (~once/day, depending on --chunk and run frequency)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--chunk",
            type=int,
            default=DEFAULT_CHUNK,
            help=f"How many streamer profiles to process this run (default {DEFAULT_CHUNK}).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset the cursor to 0 before running (start a fresh cycle).",
        )

    def handle(self, *args, **options):
        chunk = max(1, options["chunk"])
        state, _ = SearchStatsRebuildState.objects.get_or_create(pk=1)
        cursor = 0 if options["reset"] else state.last_profile_id

        profile_ids = list(
            StreamerProfile.objects
            .filter(id__gt=cursor)
            .order_by("id")
            .values_list("id", flat=True)[:chunk]
        )

        if not profile_ids:
            # Ran past the end of the set: wrap so the next run starts over.
            state.last_profile_id = 0
            state.save(update_fields=["last_profile_id", "updated_at"])
            logger.info("rebuild_search_stats: end of set reached, cursor wrapped to 0.")
            return

        created = self._rebuild_chunk(profile_ids)

        state.last_profile_id = profile_ids[-1]
        state.save(update_fields=["last_profile_id", "updated_at"])
        logger.info(
            "rebuild_search_stats: processed %s profiles (ids %s..%s), wrote %s stat rows.",
            len(profile_ids), profile_ids[0], profile_ids[-1], created,
        )

    @staticmethod
    def _rebuild_chunk(profile_ids: list[int]) -> int:
        window_start = timezone.now() - timedelta(days=WINDOW_DAYS)

        # One grouped aggregate over just this chunk's approved streams in the
        # window, split by (streamer, language) - the stats table's key.
        rows = list(
            Stream.objects
            .filter(
                streamer_profile_id__in=profile_ids,
                status=Stream.Status.APPROVED,
                finished_at__gte=window_start,
            )
            .values("streamer_profile_id", "language")
            .annotate(
                peak_viewers=Max("max_viewers"),
                avg_viewers=Avg("avg_viewers"),
                total_duration_seconds=Sum("duration"),
                streams_count=Count("id"),
                # JSONBAgg of the per-stream genre_ids arrays; flattened + de-duped below.
                genre_id_lists=JSONBAgg("genre_ids"),
            )
        )

        profile_names = {
            profile_id: (login, display_name)
            for profile_id, login, display_name in (
                StreamerProfile.objects
                .filter(id__in={row["streamer_profile_id"] for row in rows})
                .values_list("id", "host_login", "host_display_name")
            )
        }

        stats = []
        for row in rows:
            genre_ids = sorted({
                genre_id
                for one_list in (row["genre_id_lists"] or [])
                for genre_id in (one_list or [])
            })
            login, display_name = profile_names.get(row["streamer_profile_id"], ("", ""))
            stats.append(StreamerSearchStats(
                streamer_profile_id=row["streamer_profile_id"],
                language=row["language"],
                peak_viewers=row["peak_viewers"] or 0,
                avg_viewers=int(round(row["avg_viewers"] or 0)),
                total_duration_seconds=row["total_duration_seconds"] or 0,
                streams_count=row["streams_count"],
                genre_ids=genre_ids,
                host_login=login,
                host_display_name=display_name,
            ))

        with transaction.atomic():
            # Replace the chunk's rows wholesale: deleting first drops streamers
            # (and language rows) that no longer qualify in the window, so dormant
            # entries are pruned over a full cycle.
            StreamerSearchStats.objects.filter(streamer_profile_id__in=profile_ids).delete()
            StreamerSearchStats.objects.bulk_create(stats)

        return len(stats)
