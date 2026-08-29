from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .inputs import WaiverState
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams

# Bench-need fit (methodology §4.10–§4.11: "annotated with bench-need fit from
# roster construction plus the bye-crunch map"). One read per role of how badly
# Dead Parrots need a body there:
#
#   hole      a starting slot at the role is uncovered *this* week (bye/injury)
#   thin      healthy rostered depth only just covers the fixed slots
#   adequate  one spare healthy body over the fixed slots
#   deep      two or more spare
#
# plus the upcoming weeks where the role hits a bye crunch (>= warn-count
# starters out), from the same §4.4 logic the Team Outlook layer's bye-crunch
# map uses. Every free-agent entry on both lists carries the fit for its role.

__all__ = ["BenchNeedFit", "RoleDepth", "bench_need_fit", "bench_need_fits"]

RoleDepth = Literal["hole", "thin", "adequate", "deep"]


@dataclass(frozen=True)
class BenchNeedFit:
    """How well an add at ``role`` fits Dead Parrots' roster construction."""

    role: str
    fixed_slots: int
    healthy_this_week: int
    rostered_depth: int
    has_current_hole: bool
    bye_crunch_weeks: tuple[int, ...]
    depth: RoleDepth
    summary: str


def _bye_crunch_weeks(
    state: WaiverState, role: str, warn_count: int
) -> tuple[int, ...]:
    """Upcoming weeks with at least ``warn_count`` available *starters* at
    ``role`` on bye — the §4.4 warn condition, per role."""
    out: list[int] = []
    for week in state.upcoming_weeks():
        on_bye = sum(
            1
            for p in state.dead_parrots_roster
            if p.role == role
            and p.is_starter
            and p.available
            and p.bye_week == week
        )
        if on_bye >= warn_count:
            out.append(week)
    return tuple(out)


def _depth(has_hole: bool, rostered_depth: int, fixed_slots: int) -> RoleDepth:
    if has_hole:
        return "hole"
    spare = rostered_depth - fixed_slots
    if spare <= 0:
        return "thin"
    if spare == 1:
        return "adequate"
    return "deep"


def _summary(
    role: str,
    depth: RoleDepth,
    week: int,
    *,
    healthy_this_week: int,
    rostered_depth: int,
    fixed_slots: int,
    bye_crunch_weeks: tuple[int, ...],
) -> str:
    if depth == "hole":
        return (
            f"Fills a Week {week} hole at {role} — {healthy_this_week} healthy "
            f"behind {fixed_slots} starting slot(s)."
        )
    if bye_crunch_weeks:
        weeks = ", ".join(f"Week {w}" for w in bye_crunch_weeks)
        return (
            f"{role} depth for the bye crunch ({weeks}); {rostered_depth} "
            f"healthy rostered now."
        )
    if depth == "thin":
        return (
            f"{role} depth is thin — {rostered_depth} healthy for {fixed_slots} "
            f"starting slot(s), no bye crunch ahead."
        )
    return (
        f"No pressing need at {role} — {rostered_depth} healthy behind "
        f"{fixed_slots} starting slot(s)."
    )


def bench_need_fit(
    state: WaiverState,
    role: str,
    params: WaiverParams = DEFAULT_WAIVER_PARAMS,
) -> BenchNeedFit:
    """The bench-need fit for ``role`` (methodology §4.10–§4.11)."""
    fixed_slots = state.fixed_slot_needs().get(role, 0)
    healthy_this_week = state.healthy_at_role(role, state.current_week)
    rostered_depth = sum(
        1 for p in state.dead_parrots_roster if p.role == role and p.available
    )
    has_current_hole = role in state.hole_roles_resolved()
    bye_crunch_weeks = _bye_crunch_weeks(state, role, params.bye_crunch_warn_count)
    depth = _depth(has_current_hole, rostered_depth, fixed_slots)

    return BenchNeedFit(
        role=role,
        fixed_slots=fixed_slots,
        healthy_this_week=healthy_this_week,
        rostered_depth=rostered_depth,
        has_current_hole=has_current_hole,
        bye_crunch_weeks=bye_crunch_weeks,
        depth=depth,
        summary=_summary(
            role,
            depth,
            state.current_week,
            healthy_this_week=healthy_this_week,
            rostered_depth=rostered_depth,
            fixed_slots=fixed_slots,
            bye_crunch_weeks=bye_crunch_weeks,
        ),
    )


def bench_need_fits(
    state: WaiverState,
    params: WaiverParams = DEFAULT_WAIVER_PARAMS,
) -> dict[str, BenchNeedFit]:
    """The bench-need fit for every role that has a fixed starting slot, keyed
    by role."""
    return {
        role: bench_need_fit(state, role, params)
        for role in state.fixed_slot_needs()
    }
