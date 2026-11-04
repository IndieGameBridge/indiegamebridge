from django.core.management.base import BaseCommand

from apps.streams.models import Game
from core.utils.igdb_api_client import IgdbApiClient, release_date_of

# IGDB caps `where id = (...)` lists at 500 entries per request.
_IGDB_BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "One-shot backfill: fills Game.release_date from IGDB for the `isgame` rows that have an"
        " IGDB id and no date yet. Intended to run once after the migration that added the field;"
        " from then on enrich_igdb_games fills it for new games. Safe to re-run: a game IGDB has"
        " no date for stays empty and is asked for again."
    )

    def handle(self, *args, **options):
        games = list(
            Game.objects
            .filter(category=Game.Category.ISGAME, release_date__isnull=True)
            .exclude(igdb_game_id=0)
            .only("id", "igdb_game_id", "release_date")
            .order_by("id")
        )
        self.stdout.write(f"Asking IGDB for the release dates of {len(games):,} games...")

        filled = 0
        with IgdbApiClient() as client:
            for start in range(0, len(games), _IGDB_BATCH_SIZE):
                chunk = games[start:start + _IGDB_BATCH_SIZE]
                found = {item["id"]: item for item in client.get_games_by_ids([game.igdb_game_id for game in chunk])}
                changed = []
                for game in chunk:
                    game.release_date = release_date_of(found.get(game.igdb_game_id, {}))
                    if game.release_date is not None:
                        changed.append(game)
                Game.objects.bulk_update(changed, ["release_date"], batch_size=_IGDB_BATCH_SIZE)
                filled += len(changed)
                self.stdout.write(f"  ...processed {start + len(chunk):,}/{len(games):,}")

        self.stdout.write(self.style.SUCCESS(f"Filled {filled:,} release dates, of {len(games):,} games asked for."))
