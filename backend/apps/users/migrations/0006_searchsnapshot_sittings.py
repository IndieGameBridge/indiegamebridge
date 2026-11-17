from datetime import timedelta

from django.db import migrations, models

# SearchSnapshot's SITTING_GAP when this was written; a migration keeps its own copy.
SITTING_GAP = timedelta(minutes=30)


def group_into_sittings(apps, schema_editor):
    """Each user's searches less than SITTING_GAP apart become one sitting, numbered by
    its first search, and each search takes its user's staff status. The user goes next."""
    SearchSnapshot = apps.get_model("users", "SearchSnapshot")
    searches = SearchSnapshot.objects.select_related("user").order_by("user_id", "created_at")
    grouped, user_id, sitting, previous = [], None, None, None
    for search in searches.iterator(chunk_size=2000):
        if search.user_id != user_id or search.created_at - previous >= SITTING_GAP:
            user_id, sitting = search.user_id, search.pk
        previous = search.created_at
        search.sitting, search.staff = sitting, search.user.is_staff
        grouped.append(search)
    SearchSnapshot.objects.bulk_update(grouped, ["sitting", "staff"], batch_size=2000)


class Migration(migrations.Migration):
    """Searches stop naming their user. Undoing it can't bring the users back, so it only
    works on an empty table."""

    dependencies = [
        ('users', '0005_searchsnapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchsnapshot',
            name='sitting',
            field=models.PositiveBigIntegerField(null=True, help_text='The sitting the search was part of, numbered by its first search.'),
        ),
        migrations.AddField(
            model_name='searchsnapshot',
            name='staff',
            field=models.BooleanField(default=False, help_text="Whether a staff member searched, so the site's own searches can be left out."),
        ),
        migrations.RunPython(group_into_sittings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='searchsnapshot',
            name='sitting',
            field=models.PositiveBigIntegerField(help_text='The sitting the search was part of, numbered by its first search.'),
        ),
        migrations.RemoveIndex(
            model_name='searchsnapshot',
            name='users_search_user_time_idx',
        ),
        migrations.RemoveField(
            model_name='searchsnapshot',
            name='user',
        ),
        migrations.AddIndex(
            model_name='searchsnapshot',
            index=models.Index(fields=['sitting', 'created_at'], name='users_search_sitting_idx'),
        ),
    ]
