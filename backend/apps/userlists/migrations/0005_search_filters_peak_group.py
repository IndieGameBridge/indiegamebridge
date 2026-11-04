"""Drop the old Max Viewers range from the searches saved on lists.

Max Viewers was a from-and-to range, stored as peakmin and peakmax, and is now one
dropdown of size groups, stored as peak. A range can't always be told as one group, so a
saved search gets "any": a list is a snapshot, which the stored search only describes,
and without it the description would claim the form's default group.
"""

from django.db import migrations


def replace_peak_range(apps, schema_editor):
    UserListOfStreamers = apps.get_model("userlists", "UserListOfStreamers")
    changed = []
    for saved_list in UserListOfStreamers.objects.exclude(search_filters={}):
        filters = saved_list.search_filters
        if "peakmin" in filters or "peakmax" in filters:
            filters.pop("peakmin", None)
            filters.pop("peakmax", None)
            filters["peak"] = "any"
            changed.append(saved_list)
    UserListOfStreamers.objects.bulk_update(changed, ["search_filters"])


class Migration(migrations.Migration):

    dependencies = [
        ("userlists", "0004_userlistofstreamers_search_filters"),
    ]

    operations = [
        migrations.RunPython(replace_peak_range, migrations.RunPython.noop),
    ]
