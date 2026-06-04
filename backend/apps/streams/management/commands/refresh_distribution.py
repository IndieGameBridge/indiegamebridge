import logging

from django.core.management.base import BaseCommand

from apps.streams.distribution import StreamersDistribution

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Recompute the streamer peak-viewer distribution from StreamerSearchStats"
        " and store it in the cache. Intended for a scheduled (e.g. daily) run so"
        " page requests never trigger the recompute themselves."
    )

    def handle(self, *args, **options):
        StreamersDistribution.refresh()
        logger.info("Distribution cache refreshed.")
