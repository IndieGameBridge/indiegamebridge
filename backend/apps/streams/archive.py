"""What the archive commands share: the retention window, month boundaries, where the
files live, the check of a file against its record, and the lock that keeps their runs
apart."""

import hashlib
from contextlib import contextmanager
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

# Postgres keeps the current month and this many full months before it. Two months
# are never less than 59 days, so Postgres always holds at least 8 weeks.
KEEP_FULL_MONTHS = 2

# Key of the Postgres advisory lock both commands hold while they run. Any number
# works, as long as nothing else in the database locks the same one.
_LOCK_KEY = 20261026


def retention_start(now):
    """When the streams Postgres keeps start: the first moment (UTC) of the month
    KEEP_FULL_MONTHS before the current one."""
    months = now.year * 12 + now.month - 1 - KEEP_FULL_MONTHS
    return datetime(months // 12, months % 12 + 1, 1, tzinfo=dt_timezone.utc)


def month_range(month):
    """The first moment (UTC) of a month and of the one after it, from its first day."""
    start = datetime(month.year, month.month, 1, tzinfo=dt_timezone.utc)
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return start, datetime(following.year, following.month, 1, tzinfo=dt_timezone.utc)


def parse_month(raw):
    """A --month value (YYYY-MM) as the date of the month's first day."""
    try:
        return datetime.strptime(raw, "%Y-%m").date()
    except ValueError:
        raise CommandError(f"--month takes YYYY-MM, not {raw!r}.") from None


def files_dir():
    return Path(settings.ARCHIVE_DIR) / "streams"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_problem(archived_month, path):
    """Why a month's file isn't the one its record describes, or None when it is."""
    if not path.exists():
        return f"its file {path} is missing"
    if path.stat().st_size != archived_month.file_size or sha256_of(path) != archived_month.sha256:
        return f"{path} isn't the file its record describes - its size or SHA-256 differs"
    return None


@contextmanager
def archive_lock():
    """Hold the archive lock while the block runs. Yields False, without waiting,
    when another run holds it, so an export and a delete never overlap."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
        locked = cursor.fetchone()[0]
    try:
        yield locked
    finally:
        if locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
