from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException

from ..lineup import (
    RIP_TIDE_SLOTS,
    Lineup,
    LineupEvaluation,
    RecommendationEngine,
    RosterPlayer,
    assign_slots,
)
from ..simulation import SideSummary
from ..snapshot import SnapshotRecord
from ..strategy import TeamOutlook
from ..trade import TradeCandidate, TradeDesk
from ..waiver import WaiverWire
from ..weekly import AssembledWeek, WeeklyView
from .schemas import (
    ByeCrunchWeekOut,
    ByePositionOut,
    CountdownOut,
    CutdownWindowOut,
    DesperateTeamOut,
    ExpectedWinsOut,
    FreeAgentOut,
    FreeAgentsResponse,
    GapDriverOut,
    HistoryRecordOut,
    LineupSlotProjection,
    NamedLineup,
    OpportunityOut,
    PlayerActualOut,
    SideTotals,
    SignalOut,
    SnapshotOutcomeOut,
    StreamerOut,
    SwingPlayerOut,
    TeamOutlookResponse,
    TeamStrengthOut,
    ThresholdRuleOut,
    TradeCandidateOut,
    TradeDeskResponse,
    WaiverPriorityOut,
    WeeklyViewResponse,
)

# One home for the read-side response building the frontend contracts depend on:
# the four screen serializers (ADR-0013 §5), the ``?engine=`` query-param
# resolver, and the history record. The live routes (``api/weekly.py``,
# ``api/layers.py``, ``api/history.py``) and the weekly-snapshot capture
# (ADR-0014 §1) all go through here, so a stored week and the live week render
# through one implementation.

__all__ = [
    "resolve_engine",
    "serialize_free_agents",
    "serialize_history_record",
    "serialize_team_outlook",
    "serialize_trade_desk",
    "serialize_weekly_view",
    "slot_projections",
]

_ENGINES: dict[str, RecommendationEngine] = {
    "max-p-win": "max-p-win",
    "threshold-rule": "threshold-rule",
}


def resolve_engine(engine: str | None) -> RecommendationEngine:
    if engine is None:
        return "max-p-win"
    try:
        return _ENGINES[engine]
    except KeyError:
        raise HTTPException(
            422, f"unknown engine {engine!r}; expected one of {sorted(_ENGINES)}"
        ) from None


def slot_projections(
    players: Sequence[RosterPlayer], assembled: AssembledWeek
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


def serialize_weekly_view(view: WeeklyView) -> WeeklyViewResponse:
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
    current = view.current_lineup
    dp_by_id = {p.player_id: p.roster_player for p in a.dead_parrots}
    current_players = [
        dp_by_id[pid] for pid in current.player_ids if pid in dp_by_id
    ]
    current_totals: SideTotals | None = None
    current_win: float | None = None
    if current.legal and current.head_to_head is not None:
        side: SideSummary = current.head_to_head.dead_parrots
        current_totals = SideTotals(
            mean=side.mean,
            floor=side.p10,
            projection=side.p50,
            ceiling=side.p90,
            stdev=side.stdev,
            yahoo_projected_total=a.dead_parrots_yahoo_projected_total,
        )
        current_win = current.head_to_head.p_win
    return WeeklyViewResponse(
        season=a.season,
        week=a.week,
        rng_seed=a.rng_seed,
        as_of_date=a.as_of_date,
        dead_parrots_team=a.dead_parrots_team_name,
        opponent_team=a.opponent_team_name,
        opponent_assumption=view.opponent_lineup.assumption,
        opponent_notes=list(view.opponent_lineup.notes),
        opponent_likely_lineup=slot_projections(view.opponent_lineup.players, a),
        dead_parrots_totals=dp_totals,
        dead_parrots_current_totals=current_totals,
        dead_parrots_current_lineup=slot_projections(current_players, a),
        opponent_totals=opp_totals,
        favored=opt.recommendation.p_win > 0.5,
        win_probability=opt.recommendation.p_win,
        current_win_probability=current_win,
        recommended_lineup_is_current=view.recommended_is_current,
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
        recommended_lineup=slot_projections(rec.players, a),
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


def serialize_team_outlook(
    outlook: TeamOutlook, caveats: Sequence[str]
) -> TeamOutlookResponse:
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
                    ByePositionOut(
                        role=p.role,
                        starters_on_bye=p.starters_on_bye,
                        starter_names=list(p.starter_names),
                    )
                    for p in w.per_position
                ],
                reasons=list(w.reasons),
            )
            for w in outlook.bye_crunch.weeks
        ],
        caveats=list(caveats),
    )


def _trade_candidate(c: TradeCandidate) -> TradeCandidateOut:
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


def serialize_trade_desk(
    desk: TradeDesk, caveats: Sequence[str]
) -> TradeDeskResponse:
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
        buy_low=[_trade_candidate(c) for c in desk.buy_low],
        sell_high=[_trade_candidate(c) for c in desk.sell_high],
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
        caveats=list(caveats),
    )


def serialize_history_record(record: SnapshotRecord) -> HistoryRecordOut:
    """One stored week: the frozen ``captured`` payload plus its ``outcome``
    (null until games are backfilled)."""
    s = record.snapshot
    outcome_out: SnapshotOutcomeOut | None = None
    if record.outcome is not None:
        o = record.outcome
        outcome_out = SnapshotOutcomeOut(
            backfilled_at=o.backfilled_at,
            dead_parrots_total=o.dead_parrots_total,
            opponent_total=o.opponent_total,
            result=o.result,
            player_actuals=[
                PlayerActualOut(
                    player_id=p.player_id,
                    name=p.name,
                    projected_points=p.projected_points,
                    actual_points=p.actual_points,
                    delta=p.delta,
                )
                for p in o.player_actuals
            ],
        )
    return HistoryRecordOut(
        snapshot_id=s.snapshot_id,
        season=s.season,
        week=s.week,
        created_at=s.created_at,
        rng_seed=s.rng_seed,
        captured=dict(s.captured),
        outcome=outcome_out,
    )


def serialize_free_agents(
    wire: WaiverWire, caveats: Sequence[str]
) -> FreeAgentsResponse:
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
        caveats=list(caveats),
    )
