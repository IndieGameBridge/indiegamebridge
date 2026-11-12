"""Delete personal data kept past its retention period.

Sign-in records, contact messages, export records and search records each tie
a person to something they did, and the privacy policy promises they go after
12 months. Meant for a daily cron: a run with nothing to delete is four small
DELETEs.
"""

from datetime import timedelta

from django.utils import timezone

from apps.contact.models import ContactMessage
from apps.exports.models import Export
from apps.jobs.recording import RecordedCommand
from apps.users.models import LoginSnapshot, SearchSnapshot

# The period the privacy policy states; change the two together.
RETENTION = timedelta(days=365)

# (model, label, the key its run counts it by)
EXPIRING = (
    (LoginSnapshot, "sign-in records", "sign_ins"),
    (ContactMessage, "contact messages", "contact_messages"),
    (Export, "export records", "exports"),
    (SearchSnapshot, "search records", "searches"),
)


class Command(RecordedCommand):
    help = "Delete sign-in records, contact messages, export records and search records older than 12 months."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be deleted, without deleting anything.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - RETENTION
        counts = []
        for model, label, key in EXPIRING:
            expired = model.objects.filter(created_at__lt=cutoff)
            count = expired.count() if options["dry_run"] else expired.delete()[0]
            self.count(**{key: count})
            counts.append(f"{count:,} {label}")

        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(f"{verb} personal data from before {cutoff:%Y-%m-%d}: {', '.join(counts)}.")
