from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # AddIndexConcurrently must run outside a transaction.
    # AddField with a constant default is metadata-only on PostgreSQL >= 11,
    # so it stays fast regardless and is safe to run in this mode.
    atomic = False

    dependencies = [
        ("streams", "0009_streamerprofilecache"),
    ]

    operations = [
        migrations.AddField(
            model_name="stream",
            name="avg_viewers",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Mean viewers across all snapshots (sum of per-snapshot viewers / snapshot count, rounded)."
                    " Populated when the stream goes offline; live streams stay at 0."
                    " Slightly distorted by snapshots missed during API page shifts, which is acceptable here.",
            ),
        ),
        AddIndexConcurrently(
            model_name="stream",
            index=models.Index(fields=["avg_viewers"], name="stream_avg_viewers_idx"),
        ),
    ]
