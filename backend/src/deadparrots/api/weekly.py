from __future__ import annotations

from fastapi import APIRouter, Request

from ..weekly import (
    auto_fill_lineups,
    build_weekly_view,
    compute_lineup_lab,
)
from ._deps import assembled_week
from .schemas import (
    AutoFillResponse,
    LineupLabRequest,
    LineupLabResponse,
    WeeklyViewResponse,
)
from .serialize import resolve_engine, serialize_weekly_view, slot_projections

router = APIRouter(tags=["weekly"], prefix="/weekly")

# This Week + Lineup Lab (spec issue #16). The read endpoints assemble on demand
# from the latest pulls and compose the pure layers; the JSON is the stable
# contract the frontend depends on (ADR-0013 §5). Serialization lives in
# ``api/serialize.py`` so the weekly-snapshot capture (issue #17) freezes the
# same shape.


@router.get("", response_model=WeeklyViewResponse)
def weekly_view(request: Request, engine: str | None = None) -> WeeklyViewResponse:
    """The assembled This Week view: opponent + likely lineup + assumption, both
    projected totals (floor/proj/ceiling) with the Yahoo cross-check,
    favored/underdog + win%, gap drivers, swing players, and the recommended
    lineup with the floor/ceiling/max-EV lineups alongside.

    ``engine`` (``max-p-win`` default, or ``threshold-rule``) selects which
    recommendation is active — the same toggle the optimizer exposes, so the
    frontend's threshold-rule switch (user story #11) has a backend to call.
    """
    view = build_weekly_view(
        assembled_week(request), recommendation_engine=resolve_engine(engine)
    )
    return serialize_weekly_view(view)


@router.post("/lineup-lab", response_model=LineupLabResponse)
def lineup_lab(request: Request, body: LineupLabRequest) -> LineupLabResponse:
    """Score an arbitrary candidate Dead Parrots lineup — total / floor /
    ceiling / win-probability out — and mark it illegal with the reason if the
    slot counts or eligibility do not make a legal RIP TIDE lineup.
    """
    result = compute_lineup_lab(
        assembled_week(request), body.starter_ids, ir_ids=body.ir_ids
    )
    return LineupLabResponse(
        starter_ids=list(result.starter_ids),
        legal=result.legal,
        reason=result.reason,
        total=result.total,
        floor=result.floor,
        ceiling=result.ceiling,
        win_probability=result.win_probability,
        caveats=list(result.caveats),
    )


@router.get("/lineup-lab/auto", response_model=AutoFillResponse)
def lineup_lab_auto(request: Request) -> AutoFillResponse:
    """The best-floor and best-ceiling fills (plus max-P(win) / max-EV) as
    player-id lists, and the full roster with per-player projections so the Lab
    can render both side by side (user story #14).
    """
    assembled = assembled_week(request)
    fills = auto_fill_lineups(assembled)
    roster = slot_projections(
        [p.roster_player for p in assembled.dead_parrots], assembled
    )
    return AutoFillResponse(
        floor=list(fills.floor),
        ceiling=list(fills.ceiling),
        max_p_win=list(fills.max_p_win),
        max_ev=list(fills.max_ev),
        roster=roster,
        caveats=list(fills.caveats),
    )
