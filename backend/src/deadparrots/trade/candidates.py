from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .inputs import TradeDeskState, TradePlayer
from .opportunity import OpportunityScore, opportunity_score
from .params import DEFAULT_TRADE_PARAMS, TradeParams

# Buy-low / sell-high candidates (methodology §4.6–§4.8).
#
#   buy-low   opportunity trend up  while fantasy output lags   (a rival player
#             to acquire)
#   sell-high fantasy output spiking while opportunity flat/down (a Dead Parrots
#             player to trade away), weighted up for injury risk or a hard
#             upcoming schedule
#
# A player is a candidate only when, on top of the trend test, the **trade
# edge** — the positional-rank gap between the market-value proxy (external
# consensus rest-of-season rank, §4.7) and the model's opportunity-adjusted
# rank — clears roughly one positional tier in the direction the flag implies
# (§4.8). For sell-high the sell-high weight scales that edge, so a real injury
# or a brutal schedule can lift a borderline sub-tier edge over the line.

__all__ = ["TradeCandidate", "TradeSide", "trade_candidates"]

TradeSide = Literal["buy-low", "sell-high"]


@dataclass(frozen=True)
class TradeCandidate:
    """One surfaced buy-low or sell-high target.

    ``trade_edge`` is signed ``market_rank - model_rank`` — positive when the
    model ranks the player higher than the market (the buy-low direction),
    negative when lower (the sell-high direction). The surfacing filter (§4.8)
    tests the *unweighted* directional edge against ``edge_tier``:
    ``abs(trade_edge) >= edge_tier``, sub-tier is hidden unconditionally.
    ``priority`` is that directional edge scaled by ``sell_high_weight``
    (``1.0`` for buy-low; raised by injury risk / a hard schedule per §4.6) and
    is the sort key only — it never moves the threshold.
    """

    player_id: str
    name: str
    position: str
    side: TradeSide
    opportunity: OpportunityScore
    market_rank: int
    model_rank: int
    trade_edge: int
    edge_tier: int
    sell_high_weight: float
    priority: float
    reasons: tuple[str, ...]


def _model_ranks(state: TradeDeskState) -> dict[str, int]:
    """Positional rank (1 = best) of every player with a ``model_ros_points``,
    within their role, by descending points then player_id."""
    by_role: dict[str, list[TradePlayer]] = {}
    for player in state.players:
        if player.model_ros_points is not None:
            by_role.setdefault(player.role, []).append(player)

    ranks: dict[str, int] = {}
    for players in by_role.values():
        ordered = sorted(
            players,
            key=lambda p: (-(p.model_ros_points or 0.0), p.player_id),
        )
        for rank, player in enumerate(ordered, start=1):
            ranks[player.player_id] = rank
    return ranks


def _sell_high_weight(player: TradePlayer, params: TradeParams) -> tuple[float, list[str]]:
    """The sell-high edge multiplier and the reasons that raised it above 1.0."""
    weight = 1.0
    reasons: list[str] = []

    if player.injury_risk > 0.0:
        bump = params.sell_high_injury_bonus * player.injury_risk
        weight += bump
        reasons.append(
            f"Injury risk {player.injury_risk:.0%} raises the sell-high weight "
            f"by {bump:.2f} — the market is slow to price injuries in."
        )

    allowed = player.upcoming_opponent_points_allowed
    league_avg = player.league_average_points_allowed
    if allowed is not None and league_avg is not None and league_avg > 0.0:
        ratio = allowed / league_avg
        if ratio < 1.0:
            span = 1.0 - params.hard_schedule_ratio
            hardness = 1.0 if span <= 0.0 else min(1.0, (1.0 - ratio) / span)
            bump = params.sell_high_hard_schedule_bonus * hardness
            if bump > 0.0:
                weight += bump
                reasons.append(
                    f"Hard upcoming schedule — opponent allows {ratio:.2f}× the "
                    f"league average to {player.role} — raises the sell-high "
                    f"weight by {bump:.2f}."
                )

    return weight, reasons


def _trend_reason(side: TradeSide, opp: OpportunityScore) -> str:
    if side == "buy-low":
        return (
            f"Opportunity trending up ({opp.opportunity_trend:+.3f}/gm) while "
            f"points lag ({opp.output_trend:+.2f}/gm) — usage is running ahead "
            f"of output."
        )
    return (
        f"Points spiking ({opp.output_trend:+.2f}/gm) on flat-to-declining "
        f"opportunity ({opp.opportunity_trend:+.3f}/gm) — output is running "
        f"ahead of usage."
    )


def _edge_reason(
    side: TradeSide, role: str, market_rank: int, model_rank: int, tier: int
) -> str:
    better, worse = (model_rank, market_rank) if side == "buy-low" else (market_rank, model_rank)
    return (
        f"Model rest-of-season rank {role}{model_rank} vs market {role}{market_rank} "
        f"— a {abs(market_rank - model_rank)}-place gap ({better} over {worse}) "
        f"clears the {tier}-place {role} tier."
    )


def trade_candidates(
    state: TradeDeskState,
    opportunity_scores: Mapping[str, OpportunityScore] | None = None,
    params: TradeParams = DEFAULT_TRADE_PARAMS,
) -> tuple[TradeCandidate, ...]:
    """Classify and surface the buy-low / sell-high candidates in ``state``.

    ``opportunity_scores`` may be passed to reuse an already-computed map
    (``trade_desk`` does this); otherwise it is computed here. Candidates whose
    unweighted directional edge is below the one-positional-tier threshold
    (§4.8) are filtered out — the sell-high weighting affects ``priority`` and
    the sort order only, never the threshold. The result is sorted by
    descending ``priority``, then player_id.
    """
    scores = dict(opportunity_scores) if opportunity_scores is not None else {}
    model_ranks = _model_ranks(state)

    out: list[TradeCandidate] = []
    for player in state.players:
        if player.market_ros_rank is None or player.player_id not in model_ranks:
            continue
        opp = scores.get(player.player_id) or opportunity_score(player, params)
        if opp.games_counted < 2:
            continue

        opp_up = opp.opportunity_trend >= params.opportunity_up_slope
        opp_flat = opp.opportunity_trend <= params.opportunity_flat_slope
        output_lags = opp.output_trend <= params.output_lag_slope
        output_spikes = opp.output_trend >= params.output_spike_slope

        if opp_up and output_lags and not player.on_dead_parrots:
            side: TradeSide = "buy-low"
        elif output_spikes and opp_flat and player.on_dead_parrots:
            side = "sell-high"
        else:
            continue

        market_rank = player.market_ros_rank
        model_rank = model_ranks[player.player_id]
        trade_edge = market_rank - model_rank
        tier = params.edge_tier_for(player.role)

        if side == "buy-low":
            weight, weight_reasons = 1.0, []
            directional_edge = float(trade_edge)  # want model above market
        else:
            weight, weight_reasons = _sell_high_weight(player, params)
            directional_edge = float(-trade_edge)  # want model below market

        # §4.8: an edge below one positional tier is noise and is hidden,
        # unconditionally. The sell-high weight scales the ranking priority
        # only (§4.6) — it never lifts a sub-tier edge over the line.
        if directional_edge < tier:
            continue
        priority = round(directional_edge * weight, 4)

        reasons = (
            _trend_reason(side, opp),
            _edge_reason(side, player.role, market_rank, model_rank, tier),
            *weight_reasons,
        )
        out.append(
            TradeCandidate(
                player_id=player.player_id,
                name=player.name,
                position=player.position,
                side=side,
                opportunity=opp,
                market_rank=market_rank,
                model_rank=model_rank,
                trade_edge=trade_edge,
                edge_tier=tier,
                sell_high_weight=round(weight, 4),
                priority=priority,
                reasons=reasons,
            )
        )

    out.sort(key=lambda c: (-c.priority, c.player_id))
    return tuple(out)
