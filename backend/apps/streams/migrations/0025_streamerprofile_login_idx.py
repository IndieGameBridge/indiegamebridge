from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # CONCURRENTLY index builds cannot run inside a transaction. The build reads all of
    # streams_streamerprofile (millions of rows) while the site keeps writing to it.
    atomic = False

    dependencies = [
        ("streams", "0024_streamersearchstats_active_days"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="streamerprofile",
            index=models.Index(fields=["host_login"], name="streamerprofile_login_idx"),
        ),
    ]
