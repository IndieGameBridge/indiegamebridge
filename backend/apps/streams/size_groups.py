"""Streamer sizes: one set of groups by a streamer's peak viewers over the last 4 weeks,
shared by the home page's distribution chart, the streamer search and the Games page."""

from bisect import bisect_left
from typing import NamedTuple

# Streams below this many viewers don't get approved, per HomePageBuilder's methodology
# text. Used only to label the first group as "3-10" rather than "up to 10".
MIN_PEAK = 3

# Each number is the top of its group, so a streamer whose peak equals one falls in that
# group. The last group takes everything above the final number.
PEAK_THRESHOLDS = (10, 20, 50, 200)


class SizeGroup(NamedTuple):
    # What the pages show and the filters send: "11-20".
    label: str
    # The peaks it covers, both included; None on the open ends.
    low: int | None
    high: int | None


def _size_groups() -> tuple[SizeGroup, ...]:
    groups = [SizeGroup(f"{MIN_PEAK}-{PEAK_THRESHOLDS[0]}", None, PEAK_THRESHOLDS[0])]
    for below, high in zip(PEAK_THRESHOLDS, PEAK_THRESHOLDS[1:]):
        groups.append(SizeGroup(f"{below + 1}-{high}", below + 1, high))
    groups.append(SizeGroup(f"{PEAK_THRESHOLDS[-1] + 1}+", PEAK_THRESHOLDS[-1] + 1, None))
    return tuple(groups)


SIZE_GROUPS = _size_groups()
SIZE_GROUPS_BY_LABEL = {group.label: group for group in SIZE_GROUPS}

# A size filter's options: every group, and "any" for no filter.
SIZE_FILTER_VALUES = [{"v": "any", "l": "Any size"}] + [{"v": group.label, "l": group.label} for group in SIZE_GROUPS]


def size_group_index(peak: int) -> int:
    """Where in SIZE_GROUPS the group a peak falls in is."""
    return bisect_left(PEAK_THRESHOLDS, peak)
