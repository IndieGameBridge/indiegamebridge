from django.core.management.base import BaseCommand

from apps.streams.search import StreamerSearch


class Command(BaseCommand):
    help = (
        "Print EXPLAIN (ANALYZE, BUFFERS) for the streamer search query."
        " Pass filters as key=value pairs, e.g.:"
        " manage.py explain_search lang=en window=14"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filters",
            nargs="*",
            help="key=value filter pairs. Omit for the default search.",
        )

    def handle(self, *args, **options):
        raw = {}
        for pair in options["filters"]:
            key, sep, value = pair.partition("=")
            if not sep:
                self.stderr.write(f"Ignoring malformed filter (expected key=value): {pair!r}")
                continue
            raw[key] = value

        search = StreamerSearch(raw)
        queryset = StreamerSearch._aggregate_queryset(search.filters)

        self.stdout.write(f"Normalized filters: {search.filters}")
        self.stdout.write(queryset.explain(analyze=True, buffers=True, verbose=True))
