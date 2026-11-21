"""When a streamer goes live, told by where in the world it's evening at the time.

The day splits into three 8-hour windows, fixed in UTC, that together cover all 24 hours.
Each is named after the part of the world whose afternoon and evening it spans, the hours
when most viewers there watch live. So a window says when a streamer streams, not where
they live: a German who streams from 13:00 to 17:00 German time is live in Asia's evening.

rebuild_search_stats splits every stream the same way in SQL, to find the window that
holds most of each streamer's time; the profile splits a streamer's streams here, to show
the share of each.
"""

from datetime import datetime
from typing import NamedTuple

WINDOW_SECONDS = 8 * 3600
# The windows' boundaries fall at 07:00, 15:00 and 23:00 UTC. Counted in steps of 8 hours
# from 07:00 UTC on the Unix epoch's first day, a moment's step number modulo 3 is its
# window's index in WINDOWS_BY_STEP.
FIRST_BOUNDARY_SECONDS = 7 * 3600


class EveningWindow(NamedTuple):
    # What the search sends and the stats table stores.
    code: str
    # Where it's evening then, as the form and the profile name it.
    label: str
    # Its UTC hours: from start_hour, up to end_hour.
    start_hour: int
    end_hour: int

    @property
    def utc_hours(self) -> str:
        return f"{self.start_hour:02d}:00–{self.end_hour:02d}:00 UTC"


# In step order from 07:00 UTC: a step's number modulo 3 indexes this tuple.
WINDOWS_BY_STEP = (
    EveningWindow("asia", "Asia & Oceania", 7, 15),
    EveningWindow("europe", "Europe & Africa", 15, 23),
    EveningWindow("americas", "Americas", 23, 7),
)

# The order the pages list them: west to east.
EVENING_WINDOWS = (WINDOWS_BY_STEP[2], WINDOWS_BY_STEP[1], WINDOWS_BY_STEP[0])
EVENING_WINDOW_CODES = tuple(window.code for window in EVENING_WINDOWS)


def seconds_by_window(started_at: datetime, duration: int) -> dict[str, int]:
    """A stream's seconds in each window, split exactly at 07:00, 15:00 and 23:00 UTC."""
    seconds = {code: 0 for code in EVENING_WINDOW_CODES}
    if not duration or duration <= 0:
        return seconds
    start = int(started_at.timestamp()) - FIRST_BOUNDARY_SECONDS
    end = start + duration
    step = start // WINDOW_SECONDS
    while step * WINDOW_SECONDS < end:
        overlap = min(end, (step + 1) * WINDOW_SECONDS) - max(start, step * WINDOW_SECONDS)
        seconds[WINDOWS_BY_STEP[step % 3].code] += overlap
        step += 1
    return seconds


def main_window(seconds: dict[str, int]) -> str:
    """The window holding the most time; "" when there's none. On a tie the one listed
    first in EVENING_WINDOWS wins, as in rebuild_search_stats."""
    best = max(EVENING_WINDOW_CODES, key=lambda code: (seconds.get(code, 0), -EVENING_WINDOW_CODES.index(code)))
    return best if seconds.get(best, 0) > 0 else ""
