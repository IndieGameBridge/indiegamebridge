import logging

from apps.jobs.recording import RecordedCommand
from apps.streams.distribution import StreamersDistribution

logger = logging.getLogger(__name__)


class Command(RecordedCommand):
    help = (
        "Recompute the streamer peak-viewer distribution from StreamerSearchStats"
        " and store it in the cache. Intended for a scheduled (e.g. daily) run so"
        " page requests never trigger the recompute themselves."
    )

    def handle(self, *args, **options):
        StreamersDistribution.refresh()
        logger.info("Distribution cache refreshed.")
