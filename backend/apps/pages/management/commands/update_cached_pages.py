import logging

from django.core.management.base import BaseCommand

from apps.pages.cached_pages import (
    AccountPageBuilder,
    ContactPageBuilder,
    HomePageBuilder,
    LoginPageBuilder,
    OptOutPageBuilder,
    PageFooterBuilder,
    PrivacyPolicyPageBuilder,
    StreamerProfilePageBuilder,
    StreamersPageBuilder,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recomputes pre-rendered page payloads stored in the CachedPage table."

    builders = [
        PageFooterBuilder,
        HomePageBuilder,
        StreamersPageBuilder,
        StreamerProfilePageBuilder,
        AccountPageBuilder,
        OptOutPageBuilder,
        ContactPageBuilder,
        LoginPageBuilder,
        PrivacyPolicyPageBuilder,
    ]

    def handle(self, *args, **kwargs):
        logger.info("Updating cached pages...")
        for builder_cls in self.builders:
            builder_cls().run()
        logger.info("Cached pages update finished.")
