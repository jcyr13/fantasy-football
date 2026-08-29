from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..lineup import (
    RIP_TIDE_SLOTS,
    Lineup,
    OpponentLineup,
    OptimizerResult,
    RecommendationEngine,
    RosterPlayer,
    build_opponent_lineup,
    is_legal_lineup,
    optimize_lineups,
)
from ..simulation import (
    HeadToHeadResult,
    SideSummary,
    sample_lineup_totals,
    simulate_head_to_head,
    summarise_side,
)
from ..strategy import DEFAULT_STRATEGY_PARAMS, StrategyParams, TeamOutlook, team_outlook
from ..trade import DEFAULT_TRADE_PARAMS, TradeDesk, TradeParams, trade_desk
from ..waiver import DEFAULT_WAIVER_PARAMS, WaiverParams, WaiverWire, waiver_wire
from .inputs import AssembledWeek

# Compose the pure layers over one :class:`AssembledWeek` (ADR-0013 §5). This is
# what the API's read endpoints call; it does no I/O and adds no modelling — the
# optimizer, the head-to-head sim and the three strategic layers each run
# exactly as their own tickets built them.

__all__ = [
    "AutoFill",
    "CurrentLineupRead",
    "LineupLabResult",
    "WeeklyView",
    "auto_fill_lineups",
    "build_opponent",
    "build_weekly_view",
    "compute_lineup_lab",
]


@dataclass(frozen=True)
class CurrentLineupRead:
    """The Dead Parrots lineup Yahoo currently has set, scored the same way as
    the recommendation so the This Week screen can show "here is where you
    stand" next to "here is what we'd start"."""

    player_ids: tuple[str, ...]
    legal: bool
    head_to_head: HeadToHeadResult | None


@dataclass(frozen=True)
class WeeklyView:
    """Everything ``GET /api/weekly`` plus the strategic-layer endpoints need."""

    assembled: AssembledWeek
    opponent_lineup: OpponentLineup
    optimizer: OptimizerResult
    current_lineup: CurrentLineupRead
    outlook: TeamOutlook
    trade: TradeDesk
    waiver: WaiverWire

    @property
    def recommended_is_current(self) -> bool:
        return frozenset(self.current_lineup.player_ids) == frozenset(
            p.player_id for p in self.optimizer.recommendation.lineup.players
        )


@dataclass(frozen=True)
class LineupLabResult:
    """One candidate lineup's numbers for the Lineup Lab compute endpoint.

    ``total`` / ``floor`` / ``ceiling`` / ``win_probability`` are always
    computed from whatever players resolved, so the Lab stays responsive while a
    lineup is half-built; ``legal`` is the gate on trusting them. ``caveats``
    carries the assembly's disclosures (the numbers rest on the §3 projection
    baseline like every other screen)."""

    starter_ids: tuple[str, ...]
    legal: bool
    reason: str | None
    total: float
    floor: float
    ceiling: float
    win_probability: float
    side: SideSummary
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class AutoFill:
    """The four named optimizer lineups as ``player_id`` tuples, for the Lineup
    Lab's on-demand auto-fill (user story #14)."""

    floor: tuple[str, ...]
    ceiling: tuple[str, ...]
    max_p_win: tuple[str, ...]
    max_ev: tuple[str, ...]
    caveats: tuple[str, ...]


def build_opponent(assembled: AssembledWeek) -> OpponentLineup:
    return build_opponent_lineup(
        assembled.opponent_roster_players,
        yahoo_starters=assembled.opponent_yahoo_starters or None,
        prior_week_starters=assembled.opponent_prior_starters,
    )


def _current_lineup_read(
    assembled: AssembledWeek, opponent_lineup: OpponentLineup
) -> CurrentLineupRead:
    by_id = _players_by_id(assembled)
    ids = tuple(pid for pid in assembled.dead_parrots_yahoo_starters if pid in by_id)
    players = [by_id[pid] for pid in ids]
    legal = len(players) == RIP_TIDE_SLOTS.size and is_legal_lineup(players)
    h2h = (
        simulate_head_to_head(
            [p.sim for p in players],
            [p.sim for p in opponent_lineup.players],
            rng_seed=assembled.rng_seed,
        )
        if legal
        else None
    )
    return CurrentLineupRead(player_ids=ids, legal=legal, head_to_head=h2h)


def build_weekly_view(
    assembled: AssembledWeek,
    *,
    recommendation_engine: RecommendationEngine = "max-p-win",
    strategy_params: StrategyParams = DEFAULT_STRATEGY_PARAMS,
    trade_params: TradeParams = DEFAULT_TRADE_PARAMS,
    waiver_params: WaiverParams = DEFAULT_WAIVER_PARAMS,
) -> WeeklyView:
    opponent_lineup = build_opponent(assembled)
    optimizer = optimize_lineups(
        assembled.dead_parrots_roster_players,
        opponent_lineup,
        rng_seed=assembled.rng_seed,
        recommendation_engine=recommendation_engine,
    )
    current_lineup = _current_lineup_read(assembled, opponent_lineup)
    outlook = team_outlook(
        assembled.league_state,
        params=strategy_params,
        playoff_sim_seed=assembled.rng_seed,
    )
    desk = trade_desk(assembled.trade_state, params=trade_params)
    wire = waiver_wire(assembled.waiver_state, params=waiver_params)
    return WeeklyView(
        assembled=assembled,
        opponent_lineup=opponent_lineup,
        optimizer=optimizer,
        current_lineup=current_lineup,
        outlook=outlook,
        trade=desk,
        waiver=wire,
    )


def _players_by_id(assembled: AssembledWeek) -> dict[str, RosterPlayer]:
    return {p.player_id: p.roster_player for p in assembled.dead_parrots}


def compute_lineup_lab(
    assembled: AssembledWeek,
    starter_ids: Sequence[str],
    *,
    ir_ids: Sequence[str] = (),
) -> LineupLabResult:
    """Score an arbitrary candidate Dead Parrots lineup: total / floor / ceiling
    / win-probability out, illegal lineups marked with the reason (issue #16
    acceptance criterion 4). ``ir_ids`` are the roster ids the scenario has on
    IR — a starter also listed there is an illegal placement."""
    by_id = _players_by_id(assembled)
    ids = tuple(dict.fromkeys(starter_ids))
    ir = frozenset(ir_ids)
    unknown = [pid for pid in ids if pid not in by_id]

    reason: str | None = None
    if unknown:
        reason = f"not on the Dead Parrots roster: {', '.join(unknown)}"
    elif ir & set(ids):
        reason = f"started while on IR: {', '.join(sorted(ir & set(ids)))}"
    elif len(ids) != RIP_TIDE_SLOTS.size:
        reason = f"a legal lineup starts {RIP_TIDE_SLOTS.size} players, got {len(ids)}"

    known = [by_id[pid] for pid in ids if pid in by_id]
    legal = reason is None and is_legal_lineup(known)
    if reason is None and not legal:
        reason = "slot counts or eligibility do not make a legal RIP TIDE lineup"

    sims = [p.sim for p in known]
    if not sims:
        return LineupLabResult(
            starter_ids=ids,
            legal=False,
            reason=reason or "no players supplied",
            total=0.0,
            floor=0.0,
            ceiling=0.0,
            win_probability=0.0,
            side=SideSummary(mean=0.0, p10=0.0, p50=0.0, p90=0.0, stdev=0.0),
            caveats=assembled.caveats,
        )

    side = summarise_side(sample_lineup_totals(sims, rng_seed=assembled.rng_seed))
    h2h: HeadToHeadResult = simulate_head_to_head(
        sims,
        [p.sim for p in build_opponent(assembled).players],
        rng_seed=assembled.rng_seed,
    )
    return LineupLabResult(
        starter_ids=ids,
        legal=legal,
        reason=reason,
        total=side.mean,
        floor=side.p10,
        ceiling=side.p90,
        win_probability=h2h.p_win,
        side=side,
        caveats=assembled.caveats,
    )


def _ids(lineup: Lineup) -> tuple[str, ...]:
    return tuple(p.player_id for p in lineup.players)


def auto_fill_lineups(assembled: AssembledWeek) -> AutoFill:
    """The four named optimizer lineups for the Lineup Lab's on-demand
    auto-fill (user story #14)."""
    opt = build_weekly_view(assembled).optimizer
    return AutoFill(
        floor=_ids(opt.floor.lineup),
        ceiling=_ids(opt.ceiling.lineup),
        max_p_win=_ids(opt.max_p_win.lineup),
        max_ev=_ids(opt.max_ev.lineup),
        caveats=assembled.caveats,
    )
