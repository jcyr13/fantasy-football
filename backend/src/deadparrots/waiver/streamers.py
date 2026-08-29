from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .inputs import WaiverState
from .needs import BenchNeedFit, bench_need_fit, bench_need_fits
from .own_bye import OwnByeNote, own_bye_note
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams
from .priority import WaiverPriorityVerdict, priority_verdict
from .replacement import FreeAgentValue

# The this-week streamer list (methodology §4.11): a separate free-agent list
# for a *current* bye/injury hole, sorted by next-week ceiling (P90) rather than
# rest-of-season value — "who do I plug in this week", not "who do I hold". It
# is scoped to the roles Dead Parrots have a hole at right now
# (``WaiverState.hole_roles_resolved``); K / DEF / IDP dominate in practice
# because those slots are rostered one deep and a bye leaves them empty.

__all__ = ["StreamerOption", "streamer_options"]


@dataclass(frozen=True)
class StreamerOption:
    """One free agent on the this-week streamer list, annotated.

    ``next_week_ceiling`` is the sort key (§4.11). ``hole_role`` is the role
    whose hole the add would cover. ``need_fit`` / ``own_bye`` /
    ``priority_verdict`` are the same three annotations the rest-of-season list
    carries.
    """

    player_id: str
    name: str
    position: str
    role: str
    hole_role: str
    next_week_ceiling: float
    value_over_replacement: float
    rank: int
    need_fit: BenchNeedFit
    own_bye: OwnByeNote
    priority_verdict: WaiverPriorityVerdict
    reasons: tuple[str, ...]


def _reasons(
    state: WaiverState,
    role: str,
    ceiling: float,
    need_fit: BenchNeedFit,
    own_bye: OwnByeNote,
    verdict: WaiverPriorityVerdict,
) -> tuple[str, ...]:
    hole_line = (
        f"Week {state.current_week} {role} hole — "
        f"{need_fit.healthy_this_week} healthy behind {need_fit.fixed_slots} "
        f"starting slot(s)."
    )
    ceiling_line = f"Next-week ceiling {ceiling:.1f} (P90) — the streamer sort key."
    return (hole_line, ceiling_line, own_bye.note, verdict.rationale)


def streamer_options(
    state: WaiverState,
    need_fits: Mapping[str, BenchNeedFit] | None = None,
    params: WaiverParams = DEFAULT_WAIVER_PARAMS,
    *,
    ros_values: Mapping[str, FreeAgentValue] | None = None,
) -> tuple[StreamerOption, ...]:
    """The streamer list for ``state`` (methodology §4.11).

    Scoped to ``state.hole_roles_resolved()`` and sorted by descending
    next-week ceiling, then descending rest-of-season points, then
    ``player_id``. ``ros_values`` may be passed to reuse the value-over-
    replacement numbers already computed for the rest-of-season list.
    """
    fits = dict(need_fits) if need_fits is not None else bench_need_fits(state, params)
    ros = dict(ros_values) if ros_values is not None else {}
    holes = state.hole_roles_resolved()

    candidates = [fa for fa in state.free_agents if fa.role in holes]
    candidates.sort(
        key=lambda fa: (-fa.next_week_ceiling, -fa.ros_projected_points, fa.player_id)
    )

    out: list[StreamerOption] = []
    for rank, fa in enumerate(candidates, start=1):
        fit = fits.get(fa.role) or bench_need_fit(state, fa.role, params)
        known = ros.get(fa.player_id)
        vor = (
            known.value_over_replacement
            if known is not None
            else _vor(state, fa.player_id, fa.role, fa.ros_projected_points)
        )
        verdict = (
            known.priority_verdict
            if known is not None
            else priority_verdict(vor, state, params)
        )
        own_bye = known.own_bye if known is not None else own_bye_note(fa, state, fit)
        out.append(
            StreamerOption(
                player_id=fa.player_id,
                name=fa.name,
                position=fa.position,
                role=fa.role,
                hole_role=fa.role,
                next_week_ceiling=fa.next_week_ceiling,
                value_over_replacement=vor,
                rank=rank,
                need_fit=fit,
                own_bye=own_bye,
                priority_verdict=verdict,
                reasons=_reasons(
                    state, fa.role, fa.next_week_ceiling, fit, own_bye, verdict
                ),
            )
        )
    return tuple(out)


def _vor(
    state: WaiverState, player_id: str, role: str, ros_points: float
) -> float:
    """Value over replacement for a streamer not present in the rest-of-season
    map — the best *other* free agent at the role."""
    others = [
        fa.ros_projected_points
        for fa in state.free_agents
        if fa.role == role and fa.player_id != player_id
    ]
    baseline = max(others) if others else ros_points
    return round(ros_points - baseline, 4)
