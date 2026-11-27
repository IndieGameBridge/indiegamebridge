"""The game history: every game's numbers in each past month, counted from the month's
archive file into GameMonthStats.

archive_streams counts a month once, right after writing its file, and again only when the
file is rewritten without opted-out streamers, or when the pages offer other languages.
A month's numbers come from its file alone: the files split the streams by the month they
finished in, so each month's streamers are counted exactly, with nothing to add from
Postgres or from the file of another month.

The numbers count as the game pages do: approved streams; a stream counts for every game it
played, and only for categories IGDB lists as games; its length is split evenly between all
its categories. Viewers come from the snapshots: each one's viewers times its share of the
stream's length, added up for the game it saw.

The file is read a row group at a time, on one thread, and each group is summed into one
row per (game, language, streamer) before the next is read. A month of about 6.5 million
streams takes about 0.45 GB at its peak, most of it the month's 3 million such rows.
"""

from contextlib import contextmanager

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.streams.archive import file_problem, files_dir
from apps.streams.languages import ALL_LANGUAGES, LANGUAGE_NAMES, PAGE_LANGUAGES
from apps.streams.models import Game, GameMonthStats, Stream

# One int64 key packs a (game, language, streamer): the streamer's profile id in the lowest
# STREAMER_BITS, the language's place in LANGUAGE_NAMES above it, the game's place among
# the games above that.
STREAMER_BITS = 32
LANGUAGE_BITS = 5
GAME_BITS = 63 - LANGUAGE_BITS - STREAMER_BITS

# The sums of this many row groups are folded into the month's running sums at a time:
# fewer folds, but more memory between them.
MERGE_EVERY = 16

COLUMNS = ["status", "language", "streamer_profile_id", "host_game_ids", "duration", "snapshots"]

# Rows written to GameMonthStats per INSERT.
WRITE_BATCH = 5000


def needs_counting(archived_month) -> bool:
    """Whether a month's game history is missing, or older than its file, or added up
    other page languages than the pages offer now."""
    if archived_month.stats_computed_at is None:
        return True
    if archived_month.rewritten_at is not None and archived_month.rewritten_at > archived_month.stats_computed_at:
        return True
    return list(archived_month.stats_languages) != list(PAGE_LANGUAGES)


def count_month(archived_month) -> int:
    """Count a month's game history from its file into GameMonthStats, in place of the rows
    it had; returns how many rows it wrote."""
    label = f"{archived_month.month:%Y-%m}"
    path = files_dir() / archived_month.file_name
    problem = file_problem(archived_month, path)
    if problem:
        raise CommandError(f"{label}: {problem}; its game history was left as it was.")

    games = list(Game.objects.filter(category=Game.Category.ISGAME).values_list("id", "host_game_id"))
    if len(games) >= 2 ** GAME_BITS or len(LANGUAGE_NAMES) >= 2 ** LANGUAGE_BITS:
        raise CommandError(f"{label}: the games or the languages don't fit the game history's keys.")
    game_ids = [game_id for game_id, _ in games]
    host_ids = pa.array([host_id for _, host_id in games], pa.int64())

    with _lean_arrow():
        by_language, every = _count(path, host_ids)

    codes = list(LANGUAGE_NAMES)
    month = archived_month.month
    rows = (
        GameMonthStats(
            game_id=game_ids[game], month=month,
            language=codes[language] if language is not None else ALL_LANGUAGES,
            streamers=streamers, streams=streams, seconds=round(seconds),
            viewer_seconds=round(viewer_seconds), snapshot_seconds=round(snapshot_seconds),
        )
        for game, language, streamers, streams, seconds, viewer_seconds, snapshot_seconds in _rows(by_language, every)
    )
    written = 0
    with transaction.atomic():
        GameMonthStats.objects.filter(month=month).delete()
        batch = []
        for row in rows:
            batch.append(row)
            if len(batch) == WRITE_BATCH:
                GameMonthStats.objects.bulk_create(batch)
                written += len(batch)
                batch = []
        GameMonthStats.objects.bulk_create(batch)
        written += len(batch)
        archived_month.stats_computed_at = timezone.now()
        archived_month.stats_languages = list(PAGE_LANGUAGES)
        archived_month.save(update_fields=["stats_computed_at", "stats_languages"])
    return written


@contextmanager
def _lean_arrow():
    """One thread: with a thread per core, a month's count held three times the memory,
    most of it freed but not handed back. manage.py picks the system allocator, for the
    same reason."""
    cpus, io_threads = pa.cpu_count(), pa.io_thread_count()
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    try:
        yield
    finally:
        pa.set_io_thread_count(io_threads)
        pa.set_cpu_count(cpus)


def _i64(values):
    return pc.cast(values, pa.int64())


def _f64(values):
    return pc.cast(values, pa.float64())


def _fold(parts):
    """Partial sums of (key, streams, seconds) added up per key, in that column order, so
    the result folds with the next parts."""
    table = pa.concat_tables(parts).group_by("key", use_threads=False).aggregate([("streams", "sum"), ("seconds", "sum")])
    names = {"streams_sum": "streams", "seconds_sum": "seconds"}
    return table.rename_columns([names.get(name, name) for name in table.column_names]).select(["key", "streams", "seconds"])


def _count(path, host_ids):
    """The month's sums: per (game, language), and per game over the page languages, each
    as a table with the game's place in host_ids."""
    languages = pa.array(list(LANGUAGE_NAMES))
    pairs, pending, viewer_parts = None, [], []
    with pq.ParquetFile(path) as source:
        for index in range(source.num_row_groups):
            group = source.read_row_group(index, columns=COLUMNS)
            group = group.filter(pc.and_(
                pc.equal(group["status"], Stream.Status.APPROVED.value),
                pc.is_in(group["language"], value_set=languages),
            )).combine_chunks()
            if not group.num_rows:
                continue
            if pc.max(group["streamer_profile_id"]).as_py() >= 2 ** STREAMER_BITS:
                raise CommandError(f"{path.name}: a streamer profile id doesn't fit the game history's keys.")
            language = pc.index_in(group["language"], value_set=languages)
            pending.append(_streamer_sums(group, language, host_ids))
            viewer_parts.append(_viewer_sums(group, language, host_ids))
            if len(pending) >= MERGE_EVERY:
                pairs = _fold(([pairs] if pairs is not None else []) + pending)
                pending = []
    if pairs is None and not pending:
        return None, None
    pairs = _fold(([pairs] if pairs is not None else []) + pending)
    del pending

    key = pairs["key"]
    game = pc.shift_right(key, LANGUAGE_BITS + STREAMER_BITS)
    language = pc.bit_wise_and(pc.shift_right(key, STREAMER_BITS), 2 ** LANGUAGE_BITS - 1)
    streamer = pc.bit_wise_and(key, 2 ** STREAMER_BITS - 1)
    streams, seconds = pairs["streams"], pairs["seconds"]
    del pairs, key

    viewers = pa.concat_tables(viewer_parts).group_by("key", use_threads=False).aggregate(
        [("viewer_seconds", "sum"), ("snapshot_seconds", "sum")])
    viewers = pa.table({
        "game": pc.shift_right(viewers["key"], LANGUAGE_BITS),
        "language": pc.bit_wise_and(viewers["key"], 2 ** LANGUAGE_BITS - 1),
        "viewer_seconds": viewers["viewer_seconds_sum"],
        "snapshot_seconds": viewers["snapshot_seconds_sum"],
    })

    by_language = pa.table({"game": game, "language": language, "streams": streams, "seconds": seconds}) \
        .group_by(["game", "language"], use_threads=False).aggregate([("streams", "count"), ("streams", "sum"), ("seconds", "sum")]) \
        .join(viewers, ["game", "language"], join_type="left outer", use_threads=False)

    # Over the page languages, a streamer once per game, however many of them they streamed it in.
    page_languages = _page_language_places()
    page = pc.is_in(language, value_set=page_languages)
    per_streamer = pa.table({
        "key": pc.bit_wise_or(pc.shift_left(game.filter(page), STREAMER_BITS), streamer.filter(page)),
        "streams": streams.filter(page), "seconds": seconds.filter(page),
    }).group_by("key", use_threads=False).aggregate([("streams", "sum"), ("seconds", "sum")])
    page_viewers = viewers.filter(pc.is_in(viewers["language"], value_set=page_languages)) \
        .group_by("game", use_threads=False).aggregate([("viewer_seconds", "sum"), ("snapshot_seconds", "sum")])
    every = pa.table({
        "game": pc.shift_right(per_streamer["key"], STREAMER_BITS),
        "streams": per_streamer["streams_sum"], "seconds": per_streamer["seconds_sum"],
    }).group_by("game", use_threads=False).aggregate([("streams", "count"), ("streams", "sum"), ("seconds", "sum")]) \
        .join(page_viewers, "game", join_type="left outer", use_threads=False)
    return by_language, every


def _page_language_places():
    """The page languages' places in LANGUAGE_NAMES."""
    codes = list(LANGUAGE_NAMES)
    return pa.array([codes.index(code) for code in PAGE_LANGUAGES], pa.int64())


def _streamer_sums(group, language, host_ids):
    """A row group's streams and seconds per (game, language, streamer) key."""
    lists = group["host_game_ids"].chunk(0)
    parent = pc.list_parent_indices(lists)
    game = pc.index_in(pc.list_flatten(lists), value_set=host_ids)
    known = pc.is_valid(game)
    parent, game = parent.filter(known), game.filter(known)
    share = pc.divide(_f64(group["duration"]), _f64(pc.list_value_length(lists)))
    key = pc.bit_wise_or(
        pc.bit_wise_or(
            pc.shift_left(_i64(game), LANGUAGE_BITS + STREAMER_BITS),
            pc.shift_left(_i64(pc.take(language, parent)), STREAMER_BITS),
        ),
        _i64(pc.take(group["streamer_profile_id"], parent)),
    )
    sums = pa.table({"key": key, "seconds": pc.take(share, parent)}).group_by("key", use_threads=False).aggregate(
        [("seconds", "count"), ("seconds", "sum")])
    names = {"seconds_count": "streams", "seconds_sum": "seconds"}
    return sums.rename_columns([names.get(name, name) for name in sums.column_names]).select(["key", "streams", "seconds"])


def _viewer_sums(group, language, host_ids):
    """A row group's viewer-seconds and snapshot-seconds per (game, language) key."""
    snapshots = group["snapshots"].chunk(0)
    count = pc.list_value_length(snapshots)
    seen = pc.greater(count, 0)
    # Each snapshot stands for an equal share of its stream's length.
    share = pc.if_else(seen, pc.divide(_f64(group["duration"]), _f64(pc.max_element_wise(count, 1))), 0.0)
    parent = pc.list_parent_indices(snapshots)
    flat = pc.list_flatten(snapshots)
    game = pc.index_in(flat.field("g"), value_set=host_ids)
    known = pc.is_valid(game)
    parent, game = parent.filter(known), game.filter(known)
    seconds = pc.take(share, parent)
    key = pc.bit_wise_or(pc.shift_left(_i64(game), LANGUAGE_BITS), _i64(pc.take(language, parent)))
    sums = pa.table({
        "key": key,
        "viewer_seconds": pc.multiply(_f64(flat.field("v").filter(known)), seconds),
        "snapshot_seconds": seconds,
    }).group_by("key", use_threads=False).aggregate([("viewer_seconds", "sum"), ("snapshot_seconds", "sum")])
    names = {"viewer_seconds_sum": "viewer_seconds", "snapshot_seconds_sum": "snapshot_seconds"}
    return sums.rename_columns([names.get(name, name) for name in sums.column_names]) \
        .select(["key", "viewer_seconds", "snapshot_seconds"])


def _rows(by_language, every):
    """(game place, language place or None, streamers, streams, seconds, viewer-seconds,
    snapshot-seconds) for every row the month's history gets."""
    if by_language is None:
        return
    for row in by_language.to_pylist():
        yield (row["game"], row["language"], row["streams_count"], row["streams_sum"], row["seconds_sum"],
               row["viewer_seconds"] or 0.0, row["snapshot_seconds"] or 0.0)
    for row in every.to_pylist():
        yield (row["game"], None, row["streams_count"], row["streams_sum"], row["seconds_sum"],
               row["viewer_seconds_sum"] or 0.0, row["snapshot_seconds_sum"] or 0.0)
