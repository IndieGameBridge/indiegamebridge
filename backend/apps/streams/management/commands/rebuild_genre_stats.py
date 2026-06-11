import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.streams.models import (
    Game,
    GameGenre,
    GenreStats,
    GenreStatsBuildState,
    Stream,
    StreamerProfile,
)

logger = logging.getLogger(__name__)

# Fixed window: stats summarise the last 4 weeks, matching search/distribution.
WINDOW_DAYS = 28

DEFAULT_CHUNK = 20000


class Command(BaseCommand):
    help = (
        "Recompute per-genre stats for the Genre Trends page in rolling chunks."
        " Walks StreamerProfile ids behind a saved cursor, adding each chunk's"
        " contribution to draft counters; on wrapping past the end of the set it"
        " publishes the accumulated draft and resets it (one pass = one cycle)."
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
            help="Reset the cursor to 0 and zero the draft before running (start a fresh cycle).",
        )

    def handle(self, *args, **options):
        chunk = max(1, options["chunk"])
        state, _ = GenreStatsBuildState.objects.get_or_create(pk=1)

        if options["reset"]:
            self._zero_draft()
            state.last_profile_id = 0
            state.save(update_fields=["last_profile_id", "updated_at"])

        cursor = state.last_profile_id

        profile_ids = list(
            StreamerProfile.objects
            .filter(id__gt=cursor)
            .order_by("id")
            .values_list("id", flat=True)[:chunk]
        )

        if not profile_ids:
            # Ran past the end of the set: publish the completed cycle and wrap.
            self._publish_draft()
            state.last_profile_id = 0
            state.save(update_fields=["last_profile_id", "updated_at"])
            logger.info("rebuild_genre_stats: end of set reached, draft published, cursor wrapped to 0.")
            return

        self._accumulate_chunk(profile_ids)

        state.last_profile_id = profile_ids[-1]
        state.save(update_fields=["last_profile_id", "updated_at"])
        logger.info(
            "rebuild_genre_stats: processed %s profiles (ids %s..%s).",
            len(profile_ids), profile_ids[0], profile_ids[-1],
        )

    @staticmethod
    def _game_genre_map() -> dict[int, list[int]]:
        # host_game_id -> [genre host ids]. Built once per run; the game set is
        # bounded, so this stays small relative to the streams scanned per chunk.
        mapping: dict[int, list[int]] = defaultdict(list)
        for host_game_id, genre_host_id in (
            Game.objects
            .filter(genres__isnull=False)
            .values_list("host_game_id", "genres__host_genre_id")
        ):
            mapping[host_game_id].append(genre_host_id)
        return mapping

    def _accumulate_chunk(self, profile_ids: list[int]) -> None:
        window_start = timezone.now() - timedelta(days=WINDOW_DAYS)
        game_genres = self._game_genre_map()

        streams_per_genre: dict[int, int] = defaultdict(int)
        streamers_per_genre: dict[int, set[int]] = defaultdict(set)
        seconds_per_genre: dict[int, float] = defaultdict(float)

        streams = (
            Stream.objects
            .filter(
                streamer_profile_id__in=profile_ids,
                status=Stream.Status.APPROVED,
                finished_at__gte=window_start,
            )
            .values_list("streamer_profile_id", "genre_ids", "duration", "snapshots")
            .iterator(chunk_size=2000)
        )

        for profile_id, genre_ids, duration, snapshots in streams:
            # #1 streams and #2 streamers: use the stream's distinct genre list.
            for genre_id in genre_ids or ():
                streams_per_genre[genre_id] += 1
                streamers_per_genre[genre_id].add(profile_id)

            # #3 duration: split the real duration across snapshots, attributing each
            # snapshot's slice to every genre of the game it observed. Snapshots on
            # non-game categories (no genre mapping) contribute nothing, so e.g. Just
            # Chatting time falls out and per-genre seconds sum to <= duration.
            total_snapshots = len(snapshots) if snapshots else 0
            if not total_snapshots or not duration:
                continue
            per_snapshot = duration / total_snapshots
            for snapshot in snapshots:
                for genre_id in game_genres.get(snapshot.get("g"), ()):  # () when ungenred
                    seconds_per_genre[genre_id] += per_snapshot

        self._add_to_draft(streams_per_genre, streamers_per_genre, seconds_per_genre)

    @staticmethod
    def _add_to_draft(streams_per_genre, streamers_per_genre, seconds_per_genre) -> None:
        touched_ids = set(streams_per_genre) | set(seconds_per_genre)
        if not touched_ids:
            return

        # Map genre host ids -> GameGenre pks (only those defined as genres).
        genre_pk_by_host = dict(
            GameGenre.objects
            .filter(host_genre_id__in=touched_ids)
            .values_list("host_genre_id", "id")
        )

        with transaction.atomic():
            for host_id, genre_pk in genre_pk_by_host.items():
                stats, _ = GenreStats.objects.get_or_create(genre_id=genre_pk)
                GenreStats.objects.filter(pk=stats.pk).update(
                    draft_streams_count=F("draft_streams_count") + streams_per_genre.get(host_id, 0),
                    draft_streamers_count=F("draft_streamers_count") + len(streamers_per_genre.get(host_id, ())),
                    draft_total_duration_seconds=(
                        F("draft_total_duration_seconds") + round(seconds_per_genre.get(host_id, 0.0))
                    ),
                )

    @staticmethod
    def _publish_draft() -> None:
        now = timezone.now()
        with transaction.atomic():
            for stats in GenreStats.objects.all():
                stats.streams_count = stats.draft_streams_count
                stats.streamers_count = stats.draft_streamers_count
                stats.total_duration_seconds = stats.draft_total_duration_seconds
                stats.computed_at = now
                stats.draft_streams_count = 0
                stats.draft_streamers_count = 0
                stats.draft_total_duration_seconds = 0
                stats.save(update_fields=[
                    "streams_count", "streamers_count", "total_duration_seconds", "computed_at",
                    "draft_streams_count", "draft_streamers_count", "draft_total_duration_seconds",
                ])

    @staticmethod
    def _zero_draft() -> None:
        GenreStats.objects.update(
            draft_streams_count=0,
            draft_streamers_count=0,
            draft_total_duration_seconds=0,
        )
