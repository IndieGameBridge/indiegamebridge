"""Index the offline streams, for approve_streams.

approve_streams sweeps the streams that ended and aren't approved yet: a few thousand
of the tens of millions in the table. With no index on status, each run read the whole
table to find them, twice: once for the streams to approve, once for those to delete.
This partial index holds just those rows, so it stays small, and the live streams'
rewrites on every poll add nothing to it.

Built CONCURRENTLY so the fetcher keeps writing meanwhile, which can't run in a
transaction - hence atomic = False. The build reads the whole table twice.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("streams", "0018_archivedmonth_rewritten_at"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="stream",
            index=models.Index(
                fields=["id"],
                name="stream_offline_idx",
                condition=models.Q(status="offline"),
            ),
        ),
    ]
