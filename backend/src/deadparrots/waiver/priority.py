from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .inputs import WaiverState
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams

# The waiver-priority cost (methodology §4.12): waiver priority is a
# reverse-standings queue with no FAAB, and a successful claim drops Dead
# Parrots to *last*. Each free-agent target is annotated with whether the
# projected rest-of-season value-over-replacement gain justifies spending that
# priority — a qualitative flag driven by the size of the gain and the current
# queue slot. The current slot itself is surfaced once on the layer.

__all__ = [
    "WaiverPriorityStanding",
    "WaiverPriorityVerdict",
    "WaiverVerdict",
    "priority_verdict",
    "waiver_priority_standing",
]

WaiverVerdict = Literal["worth-it", "marginal", "hold-priority"]


@dataclass(frozen=True)
class WaiverPriorityStanding:
    """Dead Parrots' current slot in the reverse-standings waiver queue."""

    current_priority: int
    team_count: int
    is_last: bool
    drops_to_on_claim: int
    note: str


@dataclass(frozen=True)
class WaiverPriorityVerdict:
    """Whether a claim on one free agent is worth the waiver-priority cost."""

    verdict: WaiverVerdict
    value_over_replacement: float
    current_priority: int
    drops_to: int
    already_last: bool
    big_upgrade_points: float
    marginal_upgrade_points: float
    rationale: str


def waiver_priority_standing(state: WaiverState) -> WaiverPriorityStanding:
    """Surface the current waiver priority (methodology §4.12)."""
    is_last = state.waiver_priority >= state.team_count
    if is_last:
        note = (
            f"Dead Parrots already hold last waiver priority "
            f"({state.waiver_priority} of {state.team_count}); a successful "
            f"claim costs no queue position."
        )
    else:
        note = (
            f"Dead Parrots hold waiver priority {state.waiver_priority} of "
            f"{state.team_count}; a successful claim drops them to last "
            f"({state.team_count}). No FAAB."
        )
    return WaiverPriorityStanding(
        current_priority=state.waiver_priority,
        team_count=state.team_count,
        is_last=is_last,
        drops_to_on_claim=state.team_count,
        note=note,
    )


def priority_verdict(
    value_over_replacement: float,
    state: WaiverState,
    params: WaiverParams = DEFAULT_WAIVER_PARAMS,
) -> WaiverPriorityVerdict:
    """The worth-the-priority verdict for a gain of
    ``value_over_replacement`` rest-of-season points (methodology §4.12)."""
    priority = state.waiver_priority
    drops_to = state.team_count
    already_last = priority >= state.team_count
    # The gain is already rounded by the caller; keep it as-is so the value
    # stored here matches ``FreeAgentValue.value_over_replacement`` exactly.
    vor = value_over_replacement

    if value_over_replacement <= 0.0:
        verdict: WaiverVerdict = "hold-priority"
        rationale = (
            f"{vor:+.1f} ROS points over the best other free agent at the "
            f"position — no gain to claim."
        )
    elif already_last:
        verdict = "worth-it"
        rationale = (
            f"Dead Parrots already hold last priority — a {vor:+.1f} ROS gain "
            f"costs nothing in the queue."
        )
    elif value_over_replacement >= params.big_upgrade_points:
        verdict = "worth-it"
        rationale = (
            f"A {vor:+.1f} ROS gain clears the big-upgrade bar "
            f"({params.big_upgrade_points:.0f}); worth dropping from priority "
            f"{priority} to last."
        )
    elif (
        value_over_replacement < params.marginal_upgrade_points
        and priority <= params.protect_priority_rank
    ):
        verdict = "hold-priority"
        rationale = (
            f"A {vor:+.1f} ROS gain is below the marginal bar "
            f"({params.marginal_upgrade_points:.0f}) and Dead Parrots hold a "
            f"protected priority ({priority} of {state.team_count}) — not worth "
            f"dropping to last."
        )
    else:
        verdict = "marginal"
        rationale = (
            f"A {vor:+.1f} ROS gain sits between the marginal "
            f"({params.marginal_upgrade_points:.0f}) and big-upgrade "
            f"({params.big_upgrade_points:.0f}) bars from priority {priority} — "
            f"defensible if the bench-need fit is pressing."
        )

    return WaiverPriorityVerdict(
        verdict=verdict,
        value_over_replacement=vor,
        current_priority=priority,
        drops_to=drops_to,
        already_last=already_last,
        big_upgrade_points=params.big_upgrade_points,
        marginal_upgrade_points=params.marginal_upgrade_points,
        rationale=rationale,
    )
