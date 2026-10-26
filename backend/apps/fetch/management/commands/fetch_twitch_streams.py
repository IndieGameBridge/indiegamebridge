import logging
import time
from datetime import timedelta
import concurrent.futures

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.utils.twitch_api_client import TwitchApiClient
from apps.streams.models import StreamerProfile, Stream, Game
from apps.users.models import TwitchExclusion

logger = logging.getLogger(__name__)

# Helix `/helix/streams` accepts up to 100 `user_id` params per request.
_HELIX_BATCH_SIZE = 100

# Streams that never reach this many viewers are dropped when they're finalized,
# so polling stops paging a language once its streams fall under it.
MIN_VIEWERS_TO_KEEP = 3


class Command(BaseCommand):
    help = "Retrieves a list of streams"

    # Combined Helix request budget across all languages per poll round.
    # Together with min_time_per_poll_round this keeps the steady-state
    # request rate comfortably below the Helix 800/min limit.
    total_max_requests_per_poll_round = 0
    min_time_per_poll_round = 0

    # Actual limit of requests allowed per poll round for each language in the queue.
    # Recalculated every time when a poll is completed for a language in the queue.
    allowed_requests_per_language_poll_round = 0

    def handle(self, *args, **kwargs):
        logger.info("Starting to fetch streams...")

        # TODO LATER: use values from admin settings
        languages = ["en", "de", "fr", "es"]

        # Used to calculate limit of allowed requests per language
        # Initially all the languages are in the queue
        nof_current_languages = len(languages)

        # Per-language cap on Helix requests within a single poll round.
        # Bounds the in-memory batch each language thread accumulates before the DataBase write.
        # TODO LATER: use value from admin settings
        max_requests_per_language_poll_round = 100

        # Cron tick interval in minutes.
        # TODO LATER: use value from admin settings
        cron_interval_minutes = 15

        # TODO LATER: use value from admin settings
        self.total_max_requests_per_poll_round = 200

        # TODO LATER: use value from admin settings
        self.min_time_per_poll_round = 20

        # Per-language request budget for this poll round, taking the lower of:
        # - the global Helix budget split evenly across languages (rate-limit safety)
        # - the per-language cap (memory safety: streams accumulate in RAM until the DataBase write)
        if nof_current_languages > 0:
            self.allowed_requests_per_language_poll_round = min(round(self.total_max_requests_per_poll_round / nof_current_languages), max_requests_per_language_poll_round)

        # Safety cap on total polling time for the whole command.
        # Polling normally finishes on its own once each language's streams fall under
        # MIN_VIEWERS_TO_KEEP and its missing tracked streams are rechecked;
        # this fuse forces the command to stop before the next cron tick fires,
        # preventing two invocations from overlapping if a round is unusually slow.
        # TODO LATER: use value from admin settings
        total_max_poll_time = 900

        end_time_anchor = time.time() + total_max_poll_time

        total_collected = 0

        # Opted-out Twitch IDs to skip this run. Loaded once into a frozenset so
        # the per-stream check is an O(1) in-memory lookup (a query-per-stream
        # would be thousands of round-trips per poll round). The set is read-only
        # after this point, so it's safe to share across the language threads.
        # Staleness window: an ID that opts out mid-run isn't in this set yet, so
        # its stream may be (re)collected this round; the next run skips it.
        excluded_twitch_ids = frozenset(
            TwitchExclusion.objects.values_list("twitch_id", flat=True)
        )
        logger.info("Loaded %s excluded Twitch IDs to skip", len(excluded_twitch_ids))

        # Tracked streams the rechecks found ended, finalized below with the stale ones.
        ended_stream_ids = set()

        # Every stream seen in this run gets a finished_at no earlier than this.
        run_started_at = timezone.now()

        # Poll each language in a separate thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(languages)) as executor:
            # Schedule poll for each language and store the future objects
            future_to_poll = {
                executor.submit(
                    self._poll_streams_by_lang,
                    the_language=one_language,
                    end_time_anchor=end_time_anchor,
                    excluded_twitch_ids=excluded_twitch_ids,
                    run_started_at=run_started_at,
                ): f"Fetch streams for language: {one_language}"
                for one_language in languages
            }

            for future in concurrent.futures.as_completed(future_to_poll):
                label = future_to_poll[future]
                try:
                    collected, ended_ids = future.result()
                    total_collected += collected
                    ended_stream_ids.update(ended_ids)
                except Exception:
                    logger.exception("%s failed", label)
                logger.info("Completed - %s", label)

                # When poll for certain language is finished, then the max value of available requests for each language should be recalculated,
                # because the limits allocated to the language are now released and available for remaining languages in the queue
                nof_current_languages -= 1
                if nof_current_languages > 0:
                    self.allowed_requests_per_language_poll_round = min(round(self.total_max_requests_per_poll_round / nof_current_languages), max_requests_per_language_poll_round)

            # For every storing stream with live status and finished_at older than 4 cron time span for the polling,
            # or found ended by a recheck, finalize per-game metrics from its snapshots, mark it offline, and drop the snapshots.
            # Streams with only a single snapshot at this point are dropped entirely (insufficient data).
            stale_stream_threshold = timezone.now() - timedelta(minutes=4 * cron_interval_minutes)
            finalized_count, deleted_count = self._finalize_offline_streams(stale_stream_threshold, ended_stream_ids)

        logger.info("Total streams collected: %s", total_collected)
        logger.info("Marked %s stale streams as offline", finalized_count)
        logger.info("Dropped %s stale streams with insufficient snapshots", deleted_count)

    def _poll_streams_by_lang(self, the_language, end_time_anchor, excluded_twitch_ids=frozenset(), run_started_at=None):
        """Polls Twitch streams for one language until they fall under MIN_VIEWERS_TO_KEEP,
        the cursor is exhausted or the deadline is hit, then rechecks the tracked streams
        the poll didn't return (see `_recheck_missing_streams`).

        Runs sequential poll rounds, each issuing up to
        `self.allowed_requests_per_language_poll_round` paginated requests via
        `TwitchApiClient.iter_streams`. Sleeps the remainder of
        `self.min_time_per_poll_round` between rounds to keep the request rate
        under the Helix rate limit.

        Args:
            the_language (str): Streams language tag using an ISO 639-1 two-letter code.
            end_time_anchor (float): Soft global deadline as a `time.time()` value.
                Checked after each poll round; if exceeded, polling stops and
                whatever was collected so far is returned.
            excluded_twitch_ids (frozenset[int]): Opted-out host_user_ids to skip.
                Read-only; shared across language threads.
            run_started_at (datetime, optional): When the whole run started. A tracked
                stream last seen before it is missing from this run. Defaults to now.

        Returns:
            tuple[int, list[int]]: Total number of streams collected for this language
            across all rounds, and the ids of tracked streams the recheck found ended.
        """
        run_started_at = run_started_at or timezone.now()

        with TwitchApiClient() as client:
            dedup_ids = set()
            cursor = None
            while True:
                round_started_at = time.time()

                response_streams, cursor = client.iter_streams(
                    language=the_language,
                    end_time_anchor=end_time_anchor,
                    max_requests=self.allowed_requests_per_language_poll_round,
                    cursor=cursor,
                    min_viewers=MIN_VIEWERS_TO_KEEP,
                )

                logger.info("Unfiltered streams fetched per poll round: %s | Language: %s", len(response_streams), the_language)

                self._store_streams(response_streams, the_language, dedup_ids, excluded_twitch_ids)

                # Normal end of the language polling
                if not response_streams or not cursor:
                    break

                # Hit the global deadline. Either this language has more streams than the
                # current configuration can drain in one cron interval, or Helix is responding
                # slowly. If this fires regularly, raise the cron interval and total_max_poll_time in step.
                if time.time() >= end_time_anchor:
                    logger.warning("Stream polling terminated as time limit exceeded. Language: %s", the_language)
                    # TODO LATER: make entry for admin dashboard analytics with details about the issue
                    break

                self._sleep_rest_of_round(round_started_at, the_language)

            # Paging stopped under MIN_VIEWERS_TO_KEEP, so tracked streams that dropped
            # under it are missing from the poll, along with the ones that ended.
            ended_ids = self._recheck_missing_streams(
                client, the_language, run_started_at, end_time_anchor, round_started_at,
                dedup_ids, excluded_twitch_ids,
            )

        return len(dedup_ids), ended_ids

    def _store_streams(self, streams, the_language, dedup_ids, excluded_twitch_ids):
        """Upserts each stream's profile and row, appending one snapshot to each stream.

        Args:
            streams (list[StreamTuple]): Streams from one poll or recheck round.
            the_language (str): Streams language tag the streams are stored under.
            dedup_ids (set[int]): host_stream_ids already stored this run; updated in place.
            excluded_twitch_ids (frozenset[int]): Opted-out host_user_ids to skip.
        """
        # One shared poll timestamp for every snapshot written this round.
        # Sub-second drift across streams in the same round is irrelevant for analytics.
        poll_now = timezone.now()
        poll_timestamp = int(poll_now.timestamp())

        # Insert/update data
        with transaction.atomic():
            for one_stream in streams:

                # Skip streamers who opted out of data collection (in-memory, O(1)).
                if one_stream.host_user_id in excluded_twitch_ids:
                    continue

                # Avoid duplicated streams due to possible page shifts during the poll
                if one_stream.host_stream_id in dedup_ids:
                    continue
                dedup_ids.add(one_stream.host_stream_id)

                profile, _ = StreamerProfile.objects.get_or_create(
                    host=StreamerProfile.Host.TWITCH,
                    host_user_id=one_stream.host_user_id,
                    defaults={
                        "host_login": one_stream.host_login,
                        "host_display_name": one_stream.host_display_name,
                    }
                )

                # Update rarely changed fields on mismatch
                if (profile.host_login, profile.host_display_name) != (one_stream.host_login, one_stream.host_display_name):
                    profile.host_login = one_stream.host_login
                    profile.host_display_name = one_stream.host_display_name
                    profile.save(update_fields=["host_login", "host_display_name"])

                new_snapshot = {
                    "g": one_stream.host_game_id,
                    "v": one_stream.viewers,
                    "t": poll_timestamp,
                }

                stream, created = Stream.objects.get_or_create(
                    streamer_profile=profile,
                    host_stream_id=one_stream.host_stream_id,
                    defaults={
                        "status": Stream.Status.LIVE,
                        "language": the_language,
                        "started_at": one_stream.started_at,
                        "finished_at": poll_now,
                        "snapshots": [new_snapshot],
                    }
                )

                if not created:
                    stream.snapshots.append(new_snapshot)
                    stream.status = Stream.Status.LIVE
                    stream.language = the_language
                    stream.started_at = one_stream.started_at
                    stream.finished_at = poll_now
                    stream.save(update_fields=[
                        "status", "language", "started_at", "finished_at", "snapshots",
                    ])

    def _sleep_rest_of_round(self, round_started_at, the_language):
        """Sleeps out the rest of a poll round, keeping the request rate under the Helix limit.

        Args:
            round_started_at (float): When the round started, as a `time.time()` value.
            the_language (str): Streams language tag, for the log line.
        """
        # Respect Helix rate limits
        execution_time = round(time.time() - round_started_at)
        time_to_sleep = self.min_time_per_poll_round - execution_time
        logger.info("Execution time: %ss | Safe execution time is >= %ss | Language: %s", execution_time, self.min_time_per_poll_round, the_language)
        if time_to_sleep > 0:
            time.sleep(time_to_sleep)

    def _recheck_missing_streams(self, client, the_language, run_started_at, end_time_anchor, last_round_started_at, dedup_ids, excluded_twitch_ids):
        """Asks Twitch, by streamer, about this language's tracked streams the poll didn't return.

        A tracked stream - one that has reached MIN_VIEWERS_TO_KEEP - goes missing from
        the poll either because it dropped under that minimum or because it ended. Get
        Streams by user id tells the two apart, for 100 streamers a request: a stream
        still live gets its snapshot with the real viewer count, and the ended ones are
        returned to be finalized now rather than after the stale window.

        Streams that never reached the minimum aren't asked about, since they're dropped
        anyway. Nor is a streamer's new stream stored from here: like any other stream,
        it's tracked from when the poll first finds it at the minimum.

        Requests go out in rounds paced like the poll's and stop at the deadline. Streams
        left unasked stay live, and the stale window finalizes them if they've ended.

        Args:
            client (TwitchApiClient): The language thread's client.
            the_language (str): Streams language tag using an ISO 639-1 two-letter code.
            run_started_at (datetime): When the whole run started; streams last seen
                before it are missing from this run.
            end_time_anchor (float): Soft global deadline as a `time.time()` value.
            last_round_started_at (float): When the poll's last round started, as a
                `time.time()` value, so the first recheck round waits out its rest.
            dedup_ids (set[int]): host_stream_ids already stored this run; updated in place.
            excluded_twitch_ids (frozenset[int]): Opted-out host_user_ids to skip.

        Returns:
            list[int]: Ids of the rechecked streams that have ended.
        """
        # host_stream_id -> (id, host_user_id) for each tracked stream missing from the poll
        missing = {}
        candidates = Stream.objects.filter(
            status=Stream.Status.LIVE,
            language=the_language,
            finished_at__lt=run_started_at,
        ).values_list("id", "host_stream_id", "streamer_profile__host_user_id", "snapshots")
        for stream_id, host_stream_id, host_user_id, snapshots in candidates:
            if host_user_id in excluded_twitch_ids:
                continue
            if max((one_snapshot["v"] for one_snapshot in snapshots or []), default=0) >= MIN_VIEWERS_TO_KEEP:
                missing[host_stream_id] = (stream_id, host_user_id)

        if not missing:
            return []

        user_ids = sorted({host_user_id for _, host_user_id in missing.values()})
        batches = list(self._chunked(user_ids, _HELIX_BATCH_SIZE))
        asked_user_ids = set()
        live_stream_ids = set()
        round_started_at = last_round_started_at
        while batches and time.time() < end_time_anchor:
            self._sleep_rest_of_round(round_started_at, the_language)
            round_started_at = time.time()

            round_size = max(1, self.allowed_requests_per_language_poll_round)
            round_batches, batches = batches[:round_size], batches[round_size:]
            found_streams = []
            for one_batch in round_batches:
                found_streams.extend(
                    one_stream for one_stream in client.get_streams_by_user_ids(one_batch)
                    if one_stream.host_stream_id in missing
                )
                asked_user_ids.update(one_batch)

            live_stream_ids.update(one_stream.host_stream_id for one_stream in found_streams)
            self._store_streams(found_streams, the_language, dedup_ids, excluded_twitch_ids)

        ended_ids = [
            stream_id
            for host_stream_id, (stream_id, host_user_id) in missing.items()
            if host_user_id in asked_user_ids and host_stream_id not in live_stream_ids
        ]
        unasked_count = len(missing) - len(live_stream_ids) - len(ended_ids)
        logger.info(
            "Rechecked tracked streams missing from the poll: %s still live, %s ended, %s left unasked | Language: %s",
            len(live_stream_ids), len(ended_ids), unasked_count, the_language,
        )
        return ended_ids

    @staticmethod
    def _chunked(seq, n):
        for i in range(0, len(seq), n):
            yield seq[i:i + n]

    def _finalize_offline_streams(self, stale_stream_threshold, ended_stream_ids=()):
        """Transitions stale live streams, and those a recheck found ended, to OFFLINE and
        computes summary fields from `snapshots`.

        For each such stream, derives:
        - `max_viewers` = max viewer value observed across all snapshots (`max(s["v"] ...)`)
        - `avg_viewers` = mean viewer value across all snapshots, rounded (`sum / count`)
        - `duration`    = stream length in seconds (`finished_at - started_at`)
        - `host_game_ids`    = sorted distinct game ids observed (`sorted({s["g"] ...})`)
        Then bulk-updates status=OFFLINE plus those summary fields. Streams with
        `len(snapshots) <= 1` or `max_viewers < MIN_VIEWERS_TO_KEEP` carry too little signal
        and are dropped entirely. All writes happen in one transaction so the state stays
        consistent under failure.

        Args:
            stale_stream_threshold (datetime): Streams with status=LIVE and finished_at older than
                this are finalized.
            ended_stream_ids (Iterable[int], optional): Live streams a recheck found ended,
                finalized whatever their finished_at.

        Returns:
            tuple[int, int]: (streams transitioned to OFFLINE, streams deleted for lack of data).
        """
        stale_streams = list(
            Stream.objects.filter(status=Stream.Status.LIVE)
            .filter(Q(finished_at__lt=stale_stream_threshold) | Q(id__in=list(ended_stream_ids)))
            .only("id", "snapshots", "started_at", "finished_at")
        )

        if not stale_streams:
            return 0, 0

        insufficient_ids = []
        streams_to_update = []
        for stream in stale_streams:
            snaps = stream.snapshots or []
            if len(snaps) <= 1:
                insufficient_ids.append(stream.id)
                continue
            viewer_values = [s["v"] for s in snaps]
            max_viewers = max(viewer_values)
            if max_viewers < MIN_VIEWERS_TO_KEEP:
                insufficient_ids.append(stream.id)
                continue
            stream.status = Stream.Status.OFFLINE
            stream.max_viewers = max_viewers
            stream.avg_viewers = round(sum(viewer_values) / len(viewer_values))
            stream.duration = max(int((stream.finished_at - stream.started_at).total_seconds()), 0)
            stream.host_game_ids = sorted({s["g"] for s in snaps})
            streams_to_update.append(stream)

        with transaction.atomic():
            if insufficient_ids:
                Stream.objects.filter(id__in=insufficient_ids).delete()

            if streams_to_update:
                Stream.objects.bulk_update(
                    streams_to_update,
                    ["status", "max_viewers", "avg_viewers", "duration", "host_game_ids"],
                    batch_size=500,
                )

                # Insert placeholder Game rows for any newly observed game ids.
                # IGDB enrichment is deferred to a separate command; ignore_conflicts
                # makes this idempotent against rows already inserted by prior runs.
                observed_game_ids = {gid for stream in streams_to_update for gid in (stream.host_game_ids or [])}
                if observed_game_ids:
                    Game.objects.bulk_create(
                        [Game(host_game_id=gid) for gid in observed_game_ids],
                        batch_size=500,
                        ignore_conflicts=True,
                    )

        return len(streams_to_update), len(insufficient_ids)
