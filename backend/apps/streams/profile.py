import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.db.models import Count, Sum
from django.utils import timezone

from apps.streams.models import Game, Stream, StreamerProfile, StreamerProfileCache

logger = logging.getLogger(__name__)


STREAMER_PROFILE_CACHE_TTL = timedelta(hours=1)
STREAMER_PROFILE_STREAMS_LIMIT = 200
STREAMER_PROFILE_RECENT_WINDOW = timedelta(weeks=4)
# Number of calendar-day columns in the profile activity chart. Kept equal to the
# recent window so the chart covers exactly the same 4 weeks as the stats above it.
STREAMER_PROFILE_DAILY_DAYS = STREAMER_PROFILE_RECENT_WINDOW.days

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
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

        # Per-calendar-day activity over the recent window (drives the profile activity chart).
        daily = self._build_daily(
            recent.values("started_at", "duration", "max_viewers", "avg_viewers"),
            now,
        )

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
                "daily": daily,
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
    def _build_daily(rows, now) -> list[dict]:
        """Per-calendar-day activity over the recent window, newest day first.

        One entry per UTC day, including days with no streams, so the chart's gaps
        show how regularly the streamer goes live. Newest first because the recent
        days are the ones worth reading, and they should land at the start of the
        chart rather than off the end of its horizontal scroll. A stream is attributed
        whole to the day it started on rather than split across midnight - the chart
        answers "did they stream that day", so the start day is the meaningful bucket.
        """
        today = now.astimezone(dt_timezone.utc).date()
        first_day = today - timedelta(days=STREAMER_PROFILE_DAILY_DAYS - 1)

        buckets: dict[date, dict] = {}
        for row in rows:
            day = row["started_at"].astimezone(dt_timezone.utc).date()
            # Streams that started before the window but finished inside it fall
            # outside the labelled days and are dropped.
            if not (first_day <= day <= today):
                continue
            bucket = buckets.setdefault(day, {"seconds": 0, "peak": 0, "sum_avg": 0, "streams": 0})
            bucket["seconds"] += row["duration"] or 0
            bucket["peak"] = max(bucket["peak"], row["max_viewers"] or 0)
            bucket["sum_avg"] += row["avg_viewers"] or 0
            bucket["streams"] += 1

        daily = []
        for offset in range(STREAMER_PROFILE_DAILY_DAYS):
            day = today - timedelta(days=offset)
            bucket = buckets.get(day)
            daily.append({
                "x": f"{day:%a} {day.day}",
                # Flagged here rather than parsed back out of the label, which is
                # locale-formatted and only meant for display.
                "weekend": day.weekday() >= 5,
                # Month band under the day labels; the window spans at most two.
                "month": f"{day:%B}",
                "hours": round(bucket["seconds"] / 3600, 1) if bucket else 0,
                "peak": bucket["peak"] if bucket else 0,
                # Mean of the day's per-stream avg viewers, matching how avg is
                # aggregated elsewhere (StreamerSearchStats.avg_viewers).
                "avg": round(bucket["sum_avg"] / bucket["streams"]) if bucket else 0,
                "streams": bucket["streams"] if bucket else 0,
            })
        return daily

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
