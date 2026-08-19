import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.streams.distribution import LANGUAGES
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
            # Nothing above the cursor at all (empty table, or a reset that raced the
            # fetch cron). Publish whatever the cycle accumulated and wrap.
            self._publish_draft()
            state.last_profile_id = 0
            state.save(update_fields=["last_profile_id", "updated_at"])
            logger.info("rebuild_genre_stats: nothing to process, draft published, cursor wrapped to 0.")
            return

        self._accumulate_chunk(profile_ids)

        # A short chunk means this run reached the tail of the id range, so the cycle is
        # done: publish and wrap now instead of waiting for a run that comes back empty.
        # That empty run never happens in practice - fetch_twitch_streams inserts new
        # profiles every poll, so there are essentially always ids above the cursor -
        # which used to mean the draft was never published at all.
        end_of_set = len(profile_ids) < chunk
        if end_of_set:
            self._publish_draft()
        state.last_profile_id = 0 if end_of_set else profile_ids[-1]
        state.save(update_fields=["last_profile_id", "updated_at"])
        logger.info(
            "rebuild_genre_stats: processed %s profiles (ids %s..%s).%s",
            len(profile_ids), profile_ids[0], profile_ids[-1],
            " End of set reached, draft published, cursor wrapped to 0." if end_of_set else "",
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

        # Counters are keyed by (genre host id, language) so each genre's activity is
        # tracked per broadcast language. Only the languages the page surfaces are
        # accumulated; streams in other languages are skipped (mirrors search/distribution).
        streams_per_key: dict[tuple[int, str], int] = defaultdict(int)
        streamers_per_key: dict[tuple[int, str], set[int]] = defaultdict(set)
        seconds_per_key: dict[tuple[int, str], float] = defaultdict(float)

        streams = (
            Stream.objects
            .filter(
                streamer_profile_id__in=profile_ids,
                status=Stream.Status.APPROVED,
                finished_at__gte=window_start,
                language__in=LANGUAGES,
            )
            .values_list("streamer_profile_id", "language", "genre_ids", "duration", "snapshots")
            .iterator(chunk_size=2000)
        )

        for profile_id, language, genre_ids, duration, snapshots in streams:
            # #1 streams and #2 streamers: use the stream's distinct genre list.
            for genre_id in genre_ids or ():
                streams_per_key[(genre_id, language)] += 1
                streamers_per_key[(genre_id, language)].add(profile_id)

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
                    seconds_per_key[(genre_id, language)] += per_snapshot

        self._add_to_draft(streams_per_key, streamers_per_key, seconds_per_key)

    @staticmethod
    def _add_to_draft(streams_per_key, streamers_per_key, seconds_per_key) -> None:
        touched_keys = set(streams_per_key) | set(seconds_per_key)
        if not touched_keys:
            return

        # Map genre host ids -> GameGenre pks (only those defined as genres).
        host_ids = {host_id for host_id, _language in touched_keys}
        genre_pk_by_host = dict(
            GameGenre.objects
            .filter(host_genre_id__in=host_ids)
            .values_list("host_genre_id", "id")
        )

        with transaction.atomic():
            for host_id, language in touched_keys:
                genre_pk = genre_pk_by_host.get(host_id)
                if genre_pk is None:  # snapshot game tagged with a non-genre host id
                    continue
                key = (host_id, language)
                stats, _ = GenreStats.objects.get_or_create(genre_id=genre_pk, language=language)
                GenreStats.objects.filter(pk=stats.pk).update(
                    draft_streams_count=F("draft_streams_count") + streams_per_key.get(key, 0),
                    draft_streamers_count=F("draft_streamers_count") + len(streamers_per_key.get(key, ())),
                    draft_total_duration_seconds=(
                        F("draft_total_duration_seconds") + round(seconds_per_key.get(key, 0.0))
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
