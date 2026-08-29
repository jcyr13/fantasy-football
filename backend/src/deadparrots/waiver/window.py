from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .inputs import WaiverState
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams

# The post-roster-cutdown / practice-squad-churn waiver window (the ticket):
# flag the ~24–48h after the NFL 53-man cutdown, when cut veterans and
# practice-squad signings churn the waiver wire. The cutdown day defaults to the
# last Tuesday of August of the state's season; the window runs from that day
# through ``cutdown_window_days`` after it. Practice squads form the day after
# cutdown, which is why the window extends past the cutdown day itself.

__all__ = ["WaiverWindowFlag", "roster_cutdown_window"]

_WINDOW_NAME = "post-cutdown / practice-squad churn"


@dataclass(frozen=True)
class WaiverWindowFlag:
    """Whether the snapshot date sits in (or near) the post-cutdown churn
    window."""

    window_name: str
    opens: date
    closes: date
    as_of: date
    is_open: bool
    is_upcoming: bool
    days_until_open: int
    note: str


def roster_cutdown_window(
    state: WaiverState, params: WaiverParams = DEFAULT_WAIVER_PARAMS
) -> WaiverWindowFlag:
    """The post-cutdown waiver-window flag for ``state`` (the ticket)."""
    opens = params.cutdown_date_for(state.season)
    closes = opens + timedelta(days=params.cutdown_window_days)
    as_of = state.as_of_date

    days_until_open = (opens - as_of).days
    is_open = opens <= as_of <= closes
    is_upcoming = 0 <= days_until_open <= params.cutdown_window_lookahead_days

    if is_open:
        note = (
            f"Roster cutdowns landed {opens:%b %d}; the waiver wire is churning "
            f"with cuts and practice-squad moves through {closes:%b %d}. "
            f"Expect fresh names — hold priority for a real upgrade."
        )
    elif is_upcoming:
        note = (
            f"Roster cutdowns are {days_until_open} day(s) out ({opens:%b %d}); "
            f"a ~{params.cutdown_window_days * 24}h churn window opens then."
        )
    elif days_until_open > 0:
        note = (
            f"Roster cutdowns are {days_until_open} days out ({opens:%b %d}) — "
            f"outside the flag window for now."
        )
    else:
        note = (
            f"The post-cutdown churn window ({opens:%b %d}–{closes:%b %d}) has "
            f"passed."
        )

    return WaiverWindowFlag(
        window_name=_WINDOW_NAME,
        opens=opens,
        closes=closes,
        as_of=as_of,
        is_open=is_open,
        is_upcoming=is_upcoming,
        days_until_open=days_until_open,
        note=note,
    )
