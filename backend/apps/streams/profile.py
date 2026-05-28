import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

from apps.streams.models import Game, Stream, StreamerProfile, StreamerProfileCache

logger = logging.getLogger(__name__)


STREAMER_PROFILE_CACHE_TTL = timedelta(hours=1)
STREAMER_PROFILE_STREAMS_LIMIT = 100
STREAMER_PROFILE_RECENT_WINDOW = timedelta(weeks=4)

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
}


class StreamerProfileStreams:
    """Per-streamer cached profile payload: recent streams list + aggregate stats.

    Wraps StreamerProfileCache with TTL-on-read semantics, matching StreamerSearch.
    Each streamer's payload is computed on miss/stale and reused for an hour;
    last_hit_at is bumped on every read so cold entries can be evicted later.
    """

    def __init__(self, profile: StreamerProfile):
        self.profile = profile

    def results(self) -> dict:
        now = timezone.now()
        cached = StreamerProfileCache.objects.filter(streamer_profile_id=self.profile.id).first()

        # Pre-restructure entries stored a bare list; treat them as stale so the new shape takes over.
        fresh_enough = (
            cached
            and (now - cached.refreshed_at) < STREAMER_PROFILE_CACHE_TTL
            and isinstance(cached.content, dict)
        )

        if fresh_enough:
            StreamerProfileCache.objects.filter(pk=cached.pk).update(last_hit_at=now)
            logger.debug("Streamer profile cache hit: %s", self.profile.host_login)
            return cached.content

        logger.debug(
            "Streamer profile cache %s: %s",
            "stale" if cached else "miss",
            self.profile.host_login,
        )
        fresh = self._compute(now)
        StreamerProfileCache.objects.update_or_create(
            streamer_profile_id=self.profile.id,
            defaults={
                "content": fresh,
                "last_hit_at": now,
            },
        )
        return fresh

    def _compute(self, now) -> dict:
        approved = Stream.objects.filter(
            streamer_profile_id=self.profile.id,
            status=Stream.Status.APPROVED,
        )
        recent_cutoff = now - STREAMER_PROFILE_RECENT_WINDOW

        streams = list(
            approved
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

        # One compact scan over all approved streams yields total counts + the union of game ids,
        # split by overall vs last-4-weeks window. Snapshot blobs are not pulled.
        all_meta = list(approved.values("host_game_ids", "finished_at", "duration"))
        total_all = len(all_meta)
        total_recent = 0
        time_all = 0
        time_recent = 0
        ids_all: set[int] = set()
        ids_recent: set[int] = set()
        for row in all_meta:
            ids = row.get("host_game_ids") or []
            duration = row.get("duration") or 0
            ids_all.update(ids)
            time_all += duration
            if row["finished_at"] >= recent_cutoff:
                total_recent += 1
                time_recent += duration
                ids_recent.update(ids)

        games_index = self._build_games_index(ids_all)

        top_all = (
            approved.order_by("-max_viewers")
            .only("snapshots")
            .first()
        )
        top_recent = (
            approved.filter(finished_at__gte=recent_cutoff)
            .order_by("-max_viewers")
            .only("snapshots")
            .first()
        )

        for stream in streams:
            stream["games"] = [
                (games_index.get(gid) or {}).get("name") or "N/A"
                for gid in (stream.get("host_game_ids") or [])
            ]
            stream["started_at"] = stream["started_at"].isoformat()
            stream["finished_at"] = stream["finished_at"].isoformat()
            stream["duration"] = self._format_duration(stream["duration"])
            stream["language"] = LANGUAGE_NAMES.get(stream["language"], stream["language"])

        return {
            "streams": streams,
            "stats": {
                "all_time": {
                    "total_streams": total_all,
                    "total_time": self._format_duration(time_all),
                    "max_viewers": self._max_viewers_snapshot(top_all, games_index),
                    "games": self._games_list(ids_all, games_index),
                },
                "last_4_weeks": {
                    "total_streams": total_recent,
                    "total_time": self._format_duration(time_recent),
                    "max_viewers": self._max_viewers_snapshot(top_recent, games_index),
                    "games": self._games_list(ids_recent, games_index),
                },
            },
        }

    @staticmethod
    def _build_games_index(host_game_ids) -> dict:
        if not host_game_ids:
            return {}
        games = (
            Game.objects.filter(host_game_id__in=host_game_ids)
            .prefetch_related("genres")
        )
        return {
            game.host_game_id: {
                "name": game.host_name or "N/A",
                "genres": sorted({g.host_name for g in game.genres.all()}),
            }
            for game in games
        }

    @staticmethod
    def _games_list(host_game_ids, games_index) -> list[dict]:
        entries = [games_index[gid] for gid in host_game_ids if gid in games_index]
        return sorted(entries, key=lambda e: e["name"].lower())

    @staticmethod
    def _max_viewers_snapshot(stream, games_index) -> dict | None:
        if not stream:
            return None
        snapshots = stream.snapshots or []
        if not snapshots:
            return None
        peak = max(snapshots, key=lambda s: s.get("v", 0))
        ts = peak.get("t")
        return {
            "value": peak.get("v", 0),
            "at": datetime.fromtimestamp(ts, tz=dt_timezone.utc).isoformat() if ts else None,
            "game": (games_index.get(peak.get("g")) or {}).get("name") or "N/A",
        }

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours} h {minutes} min"
