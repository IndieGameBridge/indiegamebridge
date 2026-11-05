import logging

from django.core.management.base import CommandError

from apps.jobs.recording import RecordedCommand
from apps.pages.cached_pages import (
    AccountPageBuilder,
    ContactPageBuilder,
    DashboardPageBuilder,
    GamesPageBuilder,
    GenreTrendsPageBuilder,
    HomePageBuilder,
    ListOfStreamersPageBuilder,
    LoginPageBuilder,
    OptOutPageBuilder,
    PageFooterBuilder,
    PrivacyPolicyPageBuilder,
    StreamerProfilePageBuilder,
    StreamersPageBuilder,
)

logger = logging.getLogger(__name__)


class Command(RecordedCommand):
    help = "Recomputes pre-rendered page payloads stored in the CachedPage table."

    builders = [
        PageFooterBuilder,
        HomePageBuilder,
        GenreTrendsPageBuilder,
        GamesPageBuilder,
        StreamersPageBuilder,
        StreamerProfilePageBuilder,
        AccountPageBuilder,
        DashboardPageBuilder,
        ListOfStreamersPageBuilder,
        OptOutPageBuilder,
        ContactPageBuilder,
        LoginPageBuilder,
        PrivacyPolicyPageBuilder,
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "keys",
            nargs="*",
            help="Page keys to rebuild (e.g. 'home'). Omit to rebuild every page."
                " Use this for the hourly cron ('home' and 'streamers', whose caches hold"
                " real streamers and games); rebuild all pages when their text changes.",
        )

    def handle(self, *args, **options):
        builders_by_key = {builder_cls.key: builder_cls for builder_cls in self.builders}
        keys = options["keys"]

        if keys:
            unknown = [key for key in keys if key not in builders_by_key]
            if unknown:
                raise CommandError(
                    f"Unknown page key(s): {', '.join(unknown)}."
                    f" Available: {', '.join(sorted(builders_by_key))}."
                )
            # dict.fromkeys de-dupes while preserving the order given on the CLI.
            selected = [builders_by_key[key] for key in dict.fromkeys(keys)]
        else:
            selected = self.builders

        logger.info("Updating cached pages: %s", ", ".join(b.key for b in selected))
        for builder_cls in selected:
            builder_cls().run()
            self.count(pages=1)
        logger.info("Cached pages update finished.")
