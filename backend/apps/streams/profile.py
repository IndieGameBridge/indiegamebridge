import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db.models import Count, Sum
from django.utils import timezone

from apps.streams.models import Game, Stream, StreamerProfile, StreamerProfileCache

logger = logging.getLogger(__name__)


STREAMER_PROFILE_CACHE_TTL = timedelta(hours=1)
STREAMER_PROFILE_STREAMS_LIMIT = 200
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
        recent = approved.filter(finished_at__gte=recent_cutoff)

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

        recent_stats = recent.aggregate(
            nof_streams=Count("id"),
            total_seconds=Sum("duration"),
        )

        top_recent = recent.order_by("-max_viewers").only("snapshots").first()

        # Per-game breakdown over the recent window, folded from snapshots (one stream can span games).
        per_game_acc = self._accumulate_per_game(recent.values("duration", "snapshots"))

        # Games needing names/genres: every recent game, the games in the listed streams, and the peak game.
        ids_shown: set[int] = set(per_game_acc)
        for stream in streams:
            ids_shown.update(stream.get("host_game_ids") or [])
        if top_recent and top_recent.snapshots:
            peak_game = max(top_recent.snapshots, key=lambda s: s.get("v", 0)).get("g")
            if peak_game is not None:
                ids_shown.add(peak_game)

        games_index = self._build_games_index(ids_shown)

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
                "recent": {
                    "streams": recent_stats["nof_streams"],
                    "duration": self._format_duration(recent_stats["total_seconds"] or 0),
                    "maxv": self._max_viewers_snapshot(top_recent, games_index),
                },
                "per_game": self._build_per_game(per_game_acc, games_index),
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
    def _accumulate_per_game(rows) -> dict:
        """Fold recent streams' snapshots into per-game totals keyed by host_game_id.

        Viewer figures come from the per-snapshot game tag, and each game's share of a
        stream's running time is prorated by how many of that stream's snapshots it holds.
        """
        acc: dict[int, dict] = {}
        for row in rows:
            snapshots = row.get("snapshots") or []
            duration = row.get("duration") or 0
            in_stream: dict[int, dict] = {}
            for snap in snapshots:
                gid = snap.get("g")
                if gid is None:
                    continue
                viewers = snap.get("v") or 0
                seen = in_stream.setdefault(gid, {"n": 0, "sum_v": 0, "max_v": 0})
                seen["n"] += 1
                seen["sum_v"] += viewers
                seen["max_v"] = max(seen["max_v"], viewers)
            total_snaps = sum(seen["n"] for seen in in_stream.values())
            for gid, seen in in_stream.items():
                game = acc.setdefault(
                    gid, {"snapshots": 0, "sum_v": 0, "max_v": 0, "seconds": 0.0, "streams": 0}
                )
                game["snapshots"] += seen["n"]
                game["sum_v"] += seen["sum_v"]
                game["max_v"] = max(game["max_v"], seen["max_v"])
                game["streams"] += 1
                if total_snaps:
                    game["seconds"] += duration * seen["n"] / total_snaps
        return acc

    def _build_per_game(self, acc, games_index) -> list[dict]:
        # Most-played game first.
        ordered = sorted(acc.items(), key=lambda kv: kv[1]["seconds"], reverse=True)
        per_game = []
        for gid, game in ordered:
            info = games_index.get(gid) or {}
            snaps = game["snapshots"]
            per_game.append({
                "name": info.get("name") or "N/A",
                "genres": info.get("genres") or [],
                "duration": self._format_duration(round(game["seconds"])),
                "streams": game["streams"],
                "maxv": game["max_v"],
                "avgv": round(game["sum_v"] / snaps) if snaps else 0,
            })
        return per_game

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
            "val": peak.get("v", 0),
            "at": datetime.fromtimestamp(ts, tz=dt_timezone.utc).isoformat() if ts else None,
            "game": (games_index.get(peak.get("g")) or {}).get("name") or "N/A",
        }

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours} h {minutes} min"
