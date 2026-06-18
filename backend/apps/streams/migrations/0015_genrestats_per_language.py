# Recreate GenreStats with a (genre, language) grain.
#
# GenreStats is a disposable read-model fully rebuilt from the streams table by the
# rebuild_genre_stats cron, so we just drop and recreate it rather than back-filling a
# language for existing rows. The next rebuild cycle repopulates it.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('streams', '0014_genrestatsbuildstate_genrestats'),
    ]

    operations = [
        migrations.DeleteModel(
            name='GenreStats',
        ),
        migrations.CreateModel(
            name='GenreStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('language', models.CharField(help_text='ISO 639-1 two-letter language code these counters are scoped to.', max_length=2)),
                ('streams_count', models.PositiveBigIntegerField(default=0, help_text='Approved streams in the last 4 weeks that played at least one game of this genre. A stream spanning several genres counts once toward each.')),
                ('streamers_count', models.PositiveBigIntegerField(default=0, help_text='Distinct streamers with at least one such stream in the window.')),
                ('total_duration_seconds', models.PositiveBigIntegerField(default=0, help_text="Genre's share of streamed seconds in the window, split per stream by the fraction of snapshots on this genre's games. Non-game time (e.g. Just Chatting) is excluded.")),
                ('computed_at', models.DateTimeField(blank=True, help_text='When the published values were last swapped in (end of a full build cycle).', null=True)),
                ('draft_streams_count', models.PositiveBigIntegerField(default=0)),
                ('draft_streamers_count', models.PositiveBigIntegerField(default=0)),
                ('draft_total_duration_seconds', models.PositiveBigIntegerField(default=0)),
                ('genre', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stats', to='streams.gamegenre')),
            ],
            options={
                'unique_together': {('genre', 'language')},
            },
        ),
    ]
