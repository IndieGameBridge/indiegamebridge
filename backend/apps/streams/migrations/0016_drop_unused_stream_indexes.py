"""Drop the streams indexes nothing reads any more.

Search filters viewers, duration and genres on StreamerSearchStats, not here,
and unique_host_stream (streamer_profile, host_stream_id) serves lookups by
streamer. Every poll rewrites each live stream, adding an entry to every index
on the table, so each index dropped is less work on every poll - and about
2 GB back in production.

Dropped CONCURRENTLY so the fetcher keeps writing meanwhile, which can't run in
a transaction - hence atomic = False. Django's own operations would take a
blocking lock instead, and altering the foreign key could re-add its
constraint, which validates every row. They only update the migration state
here.
"""

import django.db.models.deletion
from django.db import migrations, models

# Index name, and the definition that recreates it on rollback.
INDEXES = [
    ("stream_duration_idx", "(duration)"),
    ("stream_avg_viewers_idx", "(avg_viewers)"),
    ("stream_genre_ids_gin", "USING gin (genre_ids)"),
    ("streams_stream_max_viewers_28e6c560", "(max_viewers)"),
    ("streams_stream_streamer_profile_id_7e16c58d", "(streamer_profile_id)"),
]


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('streams', '0015_genrestats_per_language'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    f"DROP INDEX CONCURRENTLY IF EXISTS {name};",
                    reverse_sql=f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON streams_stream {definition};",
                )
                for name, definition in INDEXES
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='stream',
                    name='stream_duration_idx',
                ),
                migrations.RemoveIndex(
                    model_name='stream',
                    name='stream_genre_ids_gin',
                ),
                migrations.RemoveIndex(
                    model_name='stream',
                    name='stream_avg_viewers_idx',
                ),
                migrations.AlterField(
                    model_name='stream',
                    name='max_viewers',
                    field=models.PositiveIntegerField(default=0, help_text='Max viewers observed across all snapshots. Populated when the stream goes offline; live streams stay at 0.'),
                ),
                migrations.AlterField(
                    model_name='stream',
                    name='streamer_profile',
                    field=models.ForeignKey(db_index=False, on_delete=django.db.models.deletion.CASCADE, related_name='streams', to='streams.streamerprofile'),
                ),
            ],
        ),
    ]
