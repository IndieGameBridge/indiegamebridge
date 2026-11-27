"""What the archive commands share: how long Postgres keeps streams, month boundaries,
where the files live, the check of a file against its record, and the lock that keeps
their runs apart."""

import hashlib
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db import connection

# Postgres keeps the streams that finished in the last 5 weeks: the 4 weeks the pages and
# the search read, and one more as a margin. Older ones live in the month files only.
KEEP_DAYS = 35

# Key of the Postgres advisory lock the archive commands hold while they run. Any number
# works, as long as nothing else in the database locks the same one.
_LOCK_KEY = 20261026


def deletion_cutoff(now):
    """Streams that finished before this leave Postgres: the start (UTC) of the day
    KEEP_DAYS before today, so every run of a day deletes up to the same moment."""
    day = now.astimezone(dt_timezone.utc).date() - timedelta(days=KEEP_DAYS)
    return datetime(day.year, day.month, day.day, tzinfo=dt_timezone.utc)


def month_start(now):
    """The first moment (UTC) of the month `now` is in: every month before it is over,
    and can have its file written."""
    now = now.astimezone(dt_timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=dt_timezone.utc)


def month_range(month):
    """The first moment (UTC) of a month and of the one after it, from its first day."""
    start = datetime(month.year, month.month, 1, tzinfo=dt_timezone.utc)
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return start, datetime(following.year, following.month, 1, tzinfo=dt_timezone.utc)


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
    when another run holds it, so the daily run and a cleanup by hand never overlap."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
        locked = cursor.fetchone()[0]
    try:
        yield locked
    finally:
        if locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
