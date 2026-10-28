"""Delete personal data kept past its retention period.

Sign-in records, contact messages and export records each tie a person to
something they did, and the privacy policy promises they go after 12 months.
Meant for a daily cron: a run with nothing to delete is three small DELETEs.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.contact.models import ContactMessage
from apps.exports.models import Export
from apps.users.models import LoginSnapshot

# The period the privacy policy states; change the two together.
RETENTION = timedelta(days=365)

EXPIRING = (
    (LoginSnapshot, "sign-in records"),
    (ContactMessage, "contact messages"),
    (Export, "export records"),
)


class Command(BaseCommand):
    help = "Delete sign-in records, contact messages and export records older than 12 months."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be deleted, without deleting anything.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - RETENTION
        counts = []
        for model, label in EXPIRING:
            expired = model.objects.filter(created_at__lt=cutoff)
            count = expired.count() if options["dry_run"] else expired.delete()[0]
            counts.append(f"{count:,} {label}")

        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(f"{verb} personal data from before {cutoff:%Y-%m-%d}: {', '.join(counts)}.")
