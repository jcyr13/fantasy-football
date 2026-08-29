from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..strategy import team_outlook
from ..trade import trade_desk
from ..waiver import waiver_wire
from ..weekly import AssembledWeek
from .schemas import (
    ByeCrunchWeekOut,
    CountdownOut,
    CutdownWindowOut,
    DesperateTeamOut,
    ExpectedWinsOut,
    FreeAgentOut,
    FreeAgentsResponse,
    OpportunityOut,
    SignalOut,
    StreamerOut,
    TeamOutlookResponse,
    TeamStrengthOut,
    TradeCandidateOut,
    TradeDeskResponse,
    WaiverPriorityOut,
)
from .weekly_sources import WeeklyDataUnavailable

router = APIRouter(tags=["layers"])

# The three strategic-layer endpoints (spec issue #16). Each assembles the week
# and runs one pure layer; ``caveats`` from the assembly rides along so the UI
# can flag the v1 approximations (ADR-0013 §4, §6).


def _assemble(request: Request) -> AssembledWeek:
    sources = getattr(request.app.state, "weekly_sources", None)
    if sources is None:
        raise HTTPException(503, "No weekly data source is configured for this server.")
    try:
        return sources.assemble()
    except WeeklyDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/team-outlook", response_model=TeamOutlookResponse)
def team_outlook_endpoint(request: Request) -> TeamOutlookResponse:
    """Team strength, expected vs actual wins, the contend/rebuild/hold signal
    with its inputs, and the bye-week crunch map with grades."""
    a = _assemble(request)
    outlook = team_outlook(a.league_state, playoff_sim_seed=a.rng_seed)
    ts = outlook.team_strength
    ew = outlook.expected_wins
    sig = outlook.signal
    return TeamOutlookResponse(
        season=outlook.season,
        week=outlook.week,
        team_strength=TeamStrengthOut(
            decay_weighted_points_for=ts.decay_weighted_points_for,
            percentile=ts.percentile,
            weeks_counted=ts.weeks_counted,
            rank=ts.dead_parrots_rank,
        ),
        expected_wins=ExpectedWinsOut(
            expected_wins=ew.expected_wins,
            actual_wins=ew.actual_wins,
            luck=ew.luck,
            weeks_counted=ew.weeks_counted,
        ),
        playoff_odds=outlook.playoff_odds.dead_parrots_odds,
        signal=SignalOut(
            signal=sig.signal,
            week=sig.week,
            signal_start_week=sig.signal_start_week,
            points_for_percentile=sig.points_for_percentile,
            playoff_odds=sig.playoff_odds,
            contend_percentile_threshold=sig.contend_percentile_threshold,
            rebuild_percentile_threshold=sig.rebuild_percentile_threshold,
            rationale=list(sig.rationale),
            recommends_transaction=sig.recommends_transaction,
        ),
        bye_crunch=[
            ByeCrunchWeekOut(
                week=w.week,
                grade=w.grade,
                max_at_one_position=w.max_at_one_position,
                can_field_legal_lineup=w.can_field_legal_lineup,
                per_position=[
                    {
                        "role": p.role,
                        "starters_on_bye": p.starters_on_bye,
                        "starter_names": list(p.starter_names),
                    }
                    for p in w.per_position
                ],
                reasons=list(w.reasons),
            )
            for w in outlook.bye_crunch.weeks
        ],
        caveats=list(a.caveats),
    )


@router.get("/trade-desk", response_model=TradeDeskResponse)
def trade_desk_endpoint(request: Request) -> TradeDeskResponse:
    """Per-player opportunity scores, buy-low/sell-high candidates with the
    market-value proxy and trade edge, the desperate-team read with reasons, and
    the November-28 countdown."""
    a = _assemble(request)
    desk = trade_desk(a.trade_state)

    def _candidate(c) -> TradeCandidateOut:
        return TradeCandidateOut(
            player_id=c.player_id,
            name=c.name,
            position=c.position,
            side=c.side,
            market_rank=c.market_rank,
            model_rank=c.model_rank,
            trade_edge=c.trade_edge,
            priority=c.priority,
            reasons=list(c.reasons),
        )

    return TradeDeskResponse(
        season=desk.season,
        week=desk.week,
        opportunity=[
            OpportunityOut(
                player_id=o.player_id,
                position=o.position,
                opportunity_index=o.opportunity_index,
                opportunity_trend=o.opportunity_trend,
                output_index=o.output_index,
                output_trend=o.output_trend,
                games_counted=o.games_counted,
            )
            for o in desk.opportunity
        ],
        buy_low=[_candidate(c) for c in desk.buy_low],
        sell_high=[_candidate(c) for c in desk.sell_high],
        desperate_teams=[
            DesperateTeamOut(
                team_id=d.team_id,
                team_name=d.team_name,
                score=d.score,
                rank=d.rank,
                reasons=list(d.reasons),
            )
            for d in desk.desperate_teams.surfaced
        ],
        countdown=CountdownOut(
            target_date=desk.countdown.target_date,
            as_of=desk.countdown.as_of,
            days_remaining=desk.countdown.days_remaining,
            is_past=desk.countdown.is_past,
        ),
        caveats=list(a.caveats),
    )


@router.get("/free-agents", response_model=FreeAgentsResponse)
def free_agents_endpoint(request: Request) -> FreeAgentsResponse:
    """The two ranked free-agent lists with bench-need fit, own byes, and the
    worth-the-priority verdict, plus the current waiver priority and the
    post-cutdown window flag."""
    a = _assemble(request)
    wire = waiver_wire(a.waiver_state)
    prio = wire.waiver_priority
    win = wire.window
    return FreeAgentsResponse(
        season=wire.season,
        week=wire.week,
        rest_of_season=[
            FreeAgentOut(
                player_id=v.player_id,
                name=v.name,
                position=v.position,
                ros_projected_points=v.ros_projected_points,
                value_over_replacement=v.value_over_replacement,
                positional_rank=v.positional_rank,
                need_fit=v.need_fit.summary,
                own_bye=v.own_bye.note,
                priority_verdict=v.priority_verdict.verdict,
                reasons=list(v.reasons),
            )
            for v in wire.rest_of_season
        ],
        streamers=[
            StreamerOut(
                player_id=s.player_id,
                name=s.name,
                position=s.position,
                hole_role=s.hole_role,
                next_week_ceiling=s.next_week_ceiling,
                need_fit=s.need_fit.summary,
                priority_verdict=s.priority_verdict.verdict,
                reasons=list(s.reasons),
            )
            for s in wire.streamers
        ],
        hole_roles=list(wire.hole_roles),
        waiver_priority=WaiverPriorityOut(
            current_priority=prio.current_priority,
            team_count=prio.team_count,
            is_last=prio.is_last,
            drops_to_on_claim=prio.drops_to_on_claim,
            note=prio.note,
        ),
        cutdown_window=CutdownWindowOut(
            window_name=win.window_name,
            opens=win.opens,
            closes=win.closes,
            is_open=win.is_open,
            is_upcoming=win.is_upcoming,
            days_until_open=win.days_until_open,
            note=win.note,
        ),
        caveats=list(a.caveats),
    )
