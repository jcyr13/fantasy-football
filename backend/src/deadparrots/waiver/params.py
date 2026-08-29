from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Every tunable in the Waiver / Free Agents layer, in one frozen table
# (methodology §4.10–§4.12 and §4.4). The signed-off ``docs/methodology.md`` §5
# parameter table stops at the Trade Desk (rows 11–12) and puts no row on the
# free-agent lists, so — apart from the bye-crunch warn count (§5 row 10, reused
# here for the per-role bye-crunch weeks) — these are build-time magnitudes,
# pinned by behaviour tests and tunable without a code change, exactly the
# treatment ADR-0010 gives the Trade Desk's trend slopes. See ADR-0011.


def last_tuesday_of_august(year: int) -> date:
    """The NFL 53-man roster cutdown day for ``year`` — the last Tuesday of
    August (the deadline has sat on that Tuesday every recent season). Practice
    squads form the next day, which is what makes the following ~48h a churn
    window on the waiver wire (methodology §4.12 addendum / the ticket)."""
    aug_31 = date(year, 8, 31)
    # date.weekday(): Monday == 0, Tuesday == 1.
    return aug_31 - timedelta(days=(aug_31.weekday() - 1) % 7)


@dataclass(frozen=True)
class WaiverParams:
    """Defaults for value-over-replacement ranking, the streamer list, the
    worth-the-priority verdict, and the post-cutdown waiver-window flag."""

    # --- worth-the-priority verdict (methodology §4.12) --------------
    # A successful claim drops Dead Parrots to last priority and there is no
    # FAAB, so the verdict trades the size of the rest-of-season
    # value-over-replacement gain against the queue slot it would cost.
    #
    # At or above ``big_upgrade_points`` of ROS value over the best other free
    # agent at the position, a claim is "worth it" whatever the queue slot.
    big_upgrade_points: float = 20.0
    # Below ``marginal_upgrade_points`` it is "hold-priority" *while* Dead
    # Parrots still hold a protected (top-half) slot; in between it is
    # "marginal".
    marginal_upgrade_points: float = 8.0
    # Holding waiver priority at this rank or better (1 = next in line) is worth
    # protecting for a merely-marginal gain. Six of a twelve-team queue — the
    # top half.
    protect_priority_rank: int = 6

    # --- per-role bye-crunch weeks (methodology §4.4 / §5 row 10) ----
    # Starters at one role on bye in an upcoming week at or above this count
    # make that a bye-crunch week for the role, surfaced in the bench-need fit.
    # Mirrors the Team Outlook layer's ``bye_crunch_warn_count`` so "crunch"
    # means the same thing in both layers.
    bye_crunch_warn_count: int = 2

    # --- post-cutdown / practice-squad-churn window (the ticket) -----
    # ``roster_cutdown_date`` defaults to the last Tuesday of August of the
    # state's season (:func:`last_tuesday_of_august`) when left ``None``.
    roster_cutdown_date: date | None = None
    # The churn window runs from the cutdown day through this many days after
    # it (the "24–48h" of the ticket, in whole days).
    cutdown_window_days: int = 2
    # The window is also flagged as *upcoming* when it opens within this many
    # days of the snapshot date.
    cutdown_window_lookahead_days: int = 7

    def __post_init__(self) -> None:
        if self.marginal_upgrade_points < 0.0:
            raise ValueError("marginal_upgrade_points must be non-negative")
        if self.big_upgrade_points < self.marginal_upgrade_points:
            raise ValueError(
                "big_upgrade_points must not be below marginal_upgrade_points"
            )
        if self.protect_priority_rank < 1:
            raise ValueError("protect_priority_rank must be >= 1")
        if self.bye_crunch_warn_count < 1:
            raise ValueError("bye_crunch_warn_count must be >= 1")
        if self.cutdown_window_days < 1:
            raise ValueError("cutdown_window_days must be >= 1")
        if self.cutdown_window_lookahead_days < 0:
            raise ValueError("cutdown_window_lookahead_days must be >= 0")

    def cutdown_date_for(self, season: int) -> date:
        """The roster-cutdown day for ``season`` — the explicit override if set,
        else the last Tuesday of August."""
        return self.roster_cutdown_date or last_tuesday_of_august(season)


DEFAULT_WAIVER_PARAMS = WaiverParams()
"""The build defaults — what ``waiver_wire`` uses unless overridden."""
