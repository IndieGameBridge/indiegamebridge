"""Let the live streams' rewrites be HOT updates.

Every poll rewrites each live stream's snapshots and finished_at. Postgres can rewrite a
row in place on its page without touching any index - a HOT update - only when no
indexed column changed and the page has room for the new version. The live index was
keyed on finished_at, so every rewrite also added an entry to every index on the table:
0.13% of updates were HOT.

- stream_live_idx replaces it, keyed on id, which never changes. The fetcher's finalizer
  still finds the live streams through it - a few tens of thousands - and checks their
  finished_at as it reads them.
- fillfactor 90 leaves a tenth of each page free, room for a rewritten row to stay on its
  page. It applies to pages written from now on.

Built CONCURRENTLY so the fetcher keeps writing meanwhile, which can't run in a
transaction - hence atomic = False. The new index is built before the old one is
dropped, so the finalizer always has one. The build reads the whole table twice.
"""

from django.contrib.postgres.operations import AddIndexConcurrently, RemoveIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("streams", "0020_one_pass_stats_rebuilds"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="stream",
            index=models.Index(
                fields=["id"],
                name="stream_live_idx",
                condition=models.Q(status="live"),
            ),
        ),
        RemoveIndexConcurrently(
            model_name="stream",
            name="stream_live_finished_at_idx",
        ),
        migrations.RunSQL(
            "ALTER TABLE streams_stream SET (fillfactor = 90);",
            reverse_sql="ALTER TABLE streams_stream RESET (fillfactor);",
        ),
    ]
