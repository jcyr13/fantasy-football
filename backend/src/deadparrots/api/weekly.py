from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Request

from ..lineup import RIP_TIDE_SLOTS, Lineup, LineupEvaluation, assign_slots
from ..weekly import (
    AssembledWeek,
    WeeklyView,
    auto_fill_lineups,
    build_weekly_view,
    compute_lineup_lab,
)
from .schemas import (
    AutoFillResponse,
    GapDriverOut,
    LineupLabRequest,
    LineupLabResponse,
    LineupSlotProjection,
    NamedLineup,
    SideTotals,
    SwingPlayerOut,
    ThresholdRuleOut,
    WeeklyViewResponse,
)
from .weekly_sources import WeeklyDataUnavailable

router = APIRouter(tags=["weekly"], prefix="/weekly")

# This Week + Lineup Lab (spec issue #16). The read endpoints assemble on demand
# from the latest pulls and compose the pure layers; the JSON is the stable
# contract the frontend depends on (ADR-0013 §5).


def _assemble(request: Request, *, week: int | None = None) -> AssembledWeek:
    sources = getattr(request.app.state, "weekly_sources", None)
    if sources is None:
        raise HTTPException(503, "No weekly data source is configured for this server.")
    try:
        return sources.assemble(week=week)
    except WeeklyDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def _slot_projections(
    players: Sequence, assembled: AssembledWeek
) -> list[LineupSlotProjection]:
    by_id = assembled.by_id()
    assignment = assign_slots(list(players), RIP_TIDE_SLOTS) or tuple(
        ("", p) for p in players
    )
    out: list[LineupSlotProjection] = []
    for slot_name, rp in assignment:
        ap = by_id.get(rp.player_id)
        proj = ap.projection if ap is not None else None
        out.append(
            LineupSlotProjection(
                player_id=rp.player_id,
                name=rp.name,
                position=rp.position,
                slot=slot_name,
                mean=rp.sim.mean,
                floor=proj.floor if proj else rp.sim.mean,
                ceiling=proj.ceiling if proj else rp.sim.mean,
                low_confidence=bool(proj.low_confidence) if proj else False,
                reasons=list(proj.reasons) if proj else [],
                resolved=bool(ap.resolved) if ap is not None else False,
            )
        )
    return out


def _named(label: str, ev: LineupEvaluation) -> NamedLineup:
    return NamedLineup(
        label=label,
        player_ids=sorted(ev.lineup.player_ids),
        win_probability=ev.p_win,
        expected_points=ev.expected_points,
        floor=ev.p10,
        ceiling=ev.p90,
    )


def _serialize_view(view: WeeklyView) -> WeeklyViewResponse:
    a = view.assembled
    opt = view.optimizer
    h2h = opt.head_to_head
    rec: Lineup = opt.recommendation.lineup

    dp_totals = SideTotals(
        mean=opt.recommendation.expected_points,
        floor=opt.recommendation.p10,
        projection=opt.recommendation.p50,
        ceiling=opt.recommendation.p90,
        stdev=h2h.dead_parrots.stdev,
        yahoo_projected_total=a.dead_parrots_yahoo_projected_total,
    )
    opp_totals = SideTotals(
        mean=h2h.opponent.mean,
        floor=h2h.opponent.p10,
        projection=h2h.opponent.p50,
        ceiling=h2h.opponent.p90,
        stdev=h2h.opponent.stdev,
        yahoo_projected_total=a.opponent_yahoo_projected_total,
    )
    return WeeklyViewResponse(
        season=a.season,
        week=a.week,
        rng_seed=a.rng_seed,
        as_of_date=a.as_of_date,
        dead_parrots_team=a.dead_parrots_team_name,
        opponent_team=a.opponent_team_name,
        opponent_assumption=view.opponent_lineup.assumption,
        opponent_notes=list(view.opponent_lineup.notes),
        opponent_likely_lineup=_slot_projections(view.opponent_lineup.players, a),
        dead_parrots_totals=dp_totals,
        opponent_totals=opp_totals,
        favored=opt.recommendation.p_win > 0.5,
        win_probability=opt.recommendation.p_win,
        mean_margin=h2h.mean_margin,
        gap_drivers=[
            GapDriverOut(
                slot=d.slot,
                dead_parrots_player=d.dead_parrots_player,
                opponent_player=d.opponent_player,
                dead_parrots_mean=d.dead_parrots_mean,
                opponent_mean=d.opponent_mean,
                contribution=d.contribution,
            )
            for d in opt.gap_drivers
        ],
        swing_players=[
            SwingPlayerOut(
                player_id=s.player_id,
                name=s.name,
                position=s.position,
                variance_share=s.variance_share,
                rank=s.rank,
            )
            for s in opt.swing_players
        ],
        recommended_lineup=_slot_projections(rec.players, a),
        recommendation_engine=opt.recommendation_engine,
        named_lineups=[
            _named("max_p_win", opt.max_p_win),
            _named("max_ev", opt.max_ev),
            _named("floor", opt.floor),
            _named("ceiling", opt.ceiling),
        ],
        threshold_rule=ThresholdRuleOut(
            branch=opt.threshold_rule.branch,
            situation_p_win=opt.threshold_rule.situation_p_win,
            favored_threshold=opt.threshold_rule.favored_threshold,
            underdog_threshold=opt.threshold_rule.underdog_threshold,
            player_ids=sorted(opt.threshold_rule.evaluation.lineup.player_ids),
        ),
        caveats=list(a.caveats),
    )


@router.get("", response_model=WeeklyViewResponse)
def weekly_view(request: Request, engine: str | None = None) -> WeeklyViewResponse:
    """The assembled This Week view: opponent + likely lineup + assumption, both
    projected totals (floor/proj/ceiling) with the Yahoo cross-check,
    favored/underdog + win%, gap drivers, swing players, and the recommended
    lineup with the floor/ceiling/max-EV lineups alongside.
    """
    assembled = _assemble(request)
    view = build_weekly_view(
        assembled,
        recommendation_engine="threshold-rule" if engine == "threshold-rule" else "max-p-win",
    )
    return _serialize_view(view)


@router.post("/lineup-lab", response_model=LineupLabResponse)
def lineup_lab(request: Request, body: LineupLabRequest) -> LineupLabResponse:
    """Score an arbitrary candidate Dead Parrots lineup — total / floor /
    ceiling / win-probability out — and mark it illegal with the reason if the
    slot counts or eligibility do not make a legal RIP TIDE lineup.
    """
    assembled = _assemble(request)
    result = compute_lineup_lab(assembled, body.starter_ids)
    return LineupLabResponse(
        starter_ids=list(result.starter_ids),
        legal=result.legal,
        reason=result.reason,
        total=result.total,
        floor=result.floor,
        ceiling=result.ceiling,
        win_probability=result.win_probability,
    )


@router.get("/lineup-lab/auto", response_model=AutoFillResponse)
def lineup_lab_auto(request: Request) -> AutoFillResponse:
    """The best-floor and best-ceiling fills (plus max-P(win) / max-EV) as
    player-id lists, and the full roster with per-player projections so the Lab
    can render both side by side (user story #14).
    """
    assembled = _assemble(request)
    fills = auto_fill_lineups(assembled)
    roster = _slot_projections(
        [p.roster_player for p in assembled.dead_parrots], assembled
    )
    return AutoFillResponse(
        floor=list(fills["floor"]),
        ceiling=list(fills["ceiling"]),
        max_p_win=list(fills["max_p_win"]),
        max_ev=list(fills["max_ev"]),
        roster=roster,
    )
