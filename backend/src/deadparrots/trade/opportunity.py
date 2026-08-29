from __future__ import annotations

from dataclasses import dataclass

from ..projection import decay_weights, weighted_mean, weighted_slope
from .inputs import TradePlayer, UsageSnapshot
from .params import DEFAULT_TRADE_PARAMS, TradeParams

# Opportunity score (methodology §4.5): one per-player index from nflverse — a
# decay-weighted composite of snap share, target share, route participation and
# red-zone share (the §3.4 signals, equal-weighted into one number) — set beside
# the player's fantasy-points trend over the same window. Buy-low / sell-high
# (§4.6) is then a comparison of the two trends; nothing here classifies.
#
# The composite and both trends are computed over the games that carry a
# ``UsageSnapshot`` (usage-less games are dropped so the opportunity and output
# series cover the *same* window, as §4.5 requires). Decay weights use the
# projection model's helpers with the Trade Desk half-life.

__all__ = ["OpportunityScore", "opportunity_score"]


@dataclass(frozen=True)
class OpportunityScore:
    """A player's role-and-usage signal beside their fantasy-points trend.

    ``opportunity_index`` is the decay-weighted mean of the equal-weighted
    four-signal composite (0–1). ``opportunity_trend`` and ``output_trend`` are
    the decay-weighted least-squares per-game slopes of the composite and of
    fantasy points respectively — positive means rising into the most recent
    games. ``games_counted`` is the number of usage-carrying games the score is
    built from; below two games both slopes are 0.0 and the player will not
    classify as a candidate.
    """

    player_id: str
    position: str
    opportunity_index: float
    opportunity_trend: float
    output_index: float
    output_trend: float
    games_counted: int
    half_life_games: float


def _composite(usage: UsageSnapshot, weights: dict[str, float]) -> float:
    """The equal-weighted four-signal usage composite for one game."""
    return (
        weights["snap_share"] * usage.snap_share
        + weights["target_share"] * usage.target_share
        + weights["route_participation"] * usage.route_participation
        + weights["red_zone_share"] * usage.red_zone_share
    )


def opportunity_score(
    player: TradePlayer, params: TradeParams = DEFAULT_TRADE_PARAMS
) -> OpportunityScore:
    """Compute ``player``'s opportunity score (methodology §4.5).

    Games are taken oldest → newest; only those with a ``UsageSnapshot`` count.
    A player with no such games gets an all-zero score (they cannot be a
    buy-low / sell-high candidate).
    """
    half_life = params.opportunity_decay_half_life_games
    weights = params.usage_weights()

    games = [w for w in sorted(player.history, key=lambda w: w.week) if w.usage is not None]
    if not games:
        return OpportunityScore(
            player_id=player.player_id,
            position=player.position,
            opportunity_index=0.0,
            opportunity_trend=0.0,
            output_index=0.0,
            output_trend=0.0,
            games_counted=0,
            half_life_games=half_life,
        )

    composite_series = [_composite(w.usage, weights) for w in games if w.usage is not None]
    points_series = [w.fantasy_points for w in games]
    decay = decay_weights(len(games), half_life)

    return OpportunityScore(
        player_id=player.player_id,
        position=player.position,
        opportunity_index=round(weighted_mean(composite_series, decay), 6),
        opportunity_trend=round(weighted_slope(composite_series, decay), 6),
        output_index=round(weighted_mean(points_series, decay), 6),
        output_trend=round(weighted_slope(points_series, decay), 6),
        games_counted=len(games),
        half_life_games=half_life,
    )
