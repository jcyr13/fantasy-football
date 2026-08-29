from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from .inputs import WaiverState
from .needs import BenchNeedFit, bench_need_fit, bench_need_fits
from .own_bye import OwnByeNote, own_bye_note
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams
from .priority import WaiverPriorityVerdict, priority_verdict

# The rest-of-season free-agent list (methodology §4.10): each free agent's
# projected points over the remaining schedule, minus a freely-available
# replacement at the same position, sorted by that value over replacement.
#
# Replacement level per position is "the best player at that position currently
# on waivers" (§4.10). Read here as the best *other* free agent at the role —
# i.e. the best alternative Dead Parrots could take instead — so the best
# available player is measured against the second best and the value over
# replacement is a genuine "how much do I gain over the next-best free option".
# A role with a single free agent has no alternative: replacement is that
# player's own number and the value over replacement is 0. See ADR-0011.

__all__ = [
    "FreeAgentValue",
    "ReplacementLevel",
    "replacement_level_for",
    "rest_of_season_value",
]


@dataclass(frozen=True)
class ReplacementLevel:
    """The freely-available replacement a free agent's value is measured
    against — the best *other* free agent at the role."""

    role: str
    points: float
    from_player_id: str | None
    from_name: str | None


@dataclass(frozen=True)
class FreeAgentValue:
    """One free agent on the rest-of-season list, fully annotated.

    ``value_over_replacement`` is ``ros_projected_points`` minus
    ``replacement.points`` — the sort key (§4.10). ``rank`` is the overall
    cross-position order (1 = best); ``positional_rank`` is the order within the
    role. ``need_fit`` is the bench-need read for the role, ``own_bye`` the
    player's own upcoming bye, and ``priority_verdict`` the worth-the-priority
    call (§4.12) — the three annotations the ticket asks for on every entry.
    """

    player_id: str
    name: str
    position: str
    role: str
    ros_projected_points: float
    replacement: ReplacementLevel
    value_over_replacement: float
    rank: int
    positional_rank: int
    need_fit: BenchNeedFit
    own_bye: OwnByeNote
    priority_verdict: WaiverPriorityVerdict
    reasons: tuple[str, ...]


def replacement_level_for(
    state: WaiverState, player_id: str, role: str
) -> ReplacementLevel:
    """The freely-available replacement one free agent's value is measured
    against — the best *other* free agent at ``role`` (methodology §4.10 read
    self-excluded, so the best available player is measured against the next
    best; see ADR-0011). A role with a single free agent has no alternative:
    the replacement is that player themselves and the value over replacement
    is 0."""
    others = [
        fa
        for fa in state.free_agents
        if fa.role == role and fa.player_id != player_id
    ]
    pool = others or [fa for fa in state.free_agents if fa.player_id == player_id]
    best = max(pool, key=lambda fa: (fa.ros_projected_points, fa.player_id))
    return ReplacementLevel(
        role=role,
        points=best.ros_projected_points,
        from_player_id=best.player_id,
        from_name=best.name,
    )


def _reasons(
    *,
    solo: bool,
    role: str,
    vor: float,
    replacement: ReplacementLevel,
    need_fit: BenchNeedFit,
    own_bye: OwnByeNote,
    verdict: WaiverPriorityVerdict,
) -> tuple[str, ...]:
    if solo:
        repl_line = (
            f"Only free agent at {role} — value over replacement is 0 by "
            f"definition."
        )
    else:
        repl_line = (
            f"{vor:+.1f} ROS points over {replacement.from_name} "
            f"({replacement.points:.1f}), the next-best free {role}."
        )
    return (repl_line, need_fit.summary, own_bye.note, verdict.rationale)


def rest_of_season_value(
    state: WaiverState,
    need_fits: Mapping[str, BenchNeedFit] | None = None,
    params: WaiverParams = DEFAULT_WAIVER_PARAMS,
) -> tuple[FreeAgentValue, ...]:
    """Rank ``state.free_agents`` by rest-of-season value over replacement
    (methodology §4.10). Sorted by descending value over replacement, then
    descending projected points, then ``player_id``."""
    fits = dict(need_fits) if need_fits is not None else bench_need_fits(state, params)

    rows: list[FreeAgentValue] = []
    for fa in state.free_agents:
        fit = fits.get(fa.role) or bench_need_fit(state, fa.role, params)
        replacement = replacement_level_for(state, fa.player_id, fa.role)
        solo = replacement.from_player_id == fa.player_id
        vor = round(fa.ros_projected_points - replacement.points, 4)
        own_bye = own_bye_note(fa, state, fit)
        verdict = priority_verdict(vor, state, params)
        rows.append(
            FreeAgentValue(
                player_id=fa.player_id,
                name=fa.name,
                position=fa.position,
                role=fa.role,
                ros_projected_points=fa.ros_projected_points,
                replacement=replacement,
                value_over_replacement=vor,
                rank=0,
                positional_rank=0,
                need_fit=fit,
                own_bye=own_bye,
                priority_verdict=verdict,
                reasons=_reasons(
                    solo=solo,
                    role=fa.role,
                    vor=vor,
                    replacement=replacement,
                    need_fit=fit,
                    own_bye=own_bye,
                    verdict=verdict,
                ),
            )
        )

    rows.sort(
        key=lambda r: (-r.value_over_replacement, -r.ros_projected_points, r.player_id)
    )
    per_role: dict[str, int] = {}
    ranked: list[FreeAgentValue] = []
    for i, row in enumerate(rows, start=1):
        per_role[row.role] = per_role.get(row.role, 0) + 1
        ranked.append(replace(row, rank=i, positional_rank=per_role[row.role]))
    return tuple(ranked)
