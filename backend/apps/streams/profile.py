import logging
from datetime import timedelta

from django.utils import timezone

from apps.streams.models import Game, Stream, StreamerProfile, StreamerProfileCache

logger = logging.getLogger(__name__)


STREAMER_PROFILE_CACHE_TTL = timedelta(hours=1)
STREAMER_PROFILE_STREAMS_LIMIT = 100


class StreamerProfileStreams:
    """Per-streamer cached list of approved streams with snapshots and game names.

    Wraps StreamerProfileCache with TTL-on-read semantics, matching StreamerSearch.
    Each streamer's payload is computed on miss/stale and reused for an hour;
    last_hit_at is bumped on every read so cold entries can be evicted later.
    """

    def __init__(self, profile: StreamerProfile):
        self.profile = profile

    def results(self) -> list[dict]:
        now = timezone.now()
        cached = StreamerProfileCache.objects.filter(streamer_profile_id=self.profile.id).first()

        if cached and (now - cached.refreshed_at) < STREAMER_PROFILE_CACHE_TTL:
            StreamerProfileCache.objects.filter(pk=cached.pk).update(last_hit_at=now)
            logger.debug("Streamer profile cache hit: %s", self.profile.host_login)
            return cached.content

        logger.debug(
            "Streamer profile cache %s: %s",
            "stale" if cached else "miss",
            self.profile.host_login,
        )
        fresh = self._compute()
        StreamerProfileCache.objects.update_or_create(
            streamer_profile_id=self.profile.id,
            defaults={
                "content": fresh,
                "last_hit_at": now,
            },
        )
        return fresh

    def _compute(self) -> list[dict]:
        streams = list(
            Stream.objects
            .filter(streamer_profile_id=self.profile.id, status=Stream.Status.APPROVED)
            .order_by("-finished_at")
            .values(
                "id",
                "language",
                "max_viewers",
                "duration",
                "started_at",
                "finished_at",
                "snapshots",
                "host_game_ids",
            )[:STREAMER_PROFILE_STREAMS_LIMIT]
        )

        all_game_ids = {
            game_id
            for stream in streams
            for game_id in (stream.get("host_game_ids") or [])
        }
        game_names = dict(
            Game.objects
            .filter(host_game_id__in=all_game_ids)
            .values_list("host_game_id", "host_name")
        )

        for stream in streams:
            stream["games"] = [
                game_names.get(game_id, "N/A")
                for game_id in (stream.get("host_game_ids") or [])
            ]
            stream.pop("host_game_ids", None)
            stream["started_at"] = stream["started_at"].isoformat()
            stream["finished_at"] = stream["finished_at"].isoformat()

        return streams
