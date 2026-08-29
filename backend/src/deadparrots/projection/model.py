from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from ..scoring import round_points
from .decay import decay_weights, weighted_slope
from .inputs import MatchupContext, OpportunityMetrics, PlayerGame, PlayerHistory
from .params import DEFAULT_PARAMS, ProjectionParams
from .residuals import (
    POSITIONAL_RESIDUAL_PRIORS,
    ResidualPrior,
    own_residual_shape,
    prior_for_position,
)

# ``project`` — the function issue #9 asks for:
#
#   (player_history, opportunity_metrics, consensus_feed, params, rng_seed)
#     -> weekly RIP TIDE point distribution, summarised as
#        floor (P10) / projection (P50) / ceiling (P90)
#
# It is pure: no I/O, no clock, no globals. The distribution is built by seeded
# Monte-Carlo over a positional-residual shape centred on an opportunity-model
# mean, so identical inputs and seed give byte-identical output (acceptance
# criterion 5). Every methodology parameter it uses lives in
# :class:`ProjectionParams`; every intermediate it computes is returned in
# :class:`ProjectionComponents` for the UI drill-down and the regression
# fixtures.


class InsufficientDataError(ValueError):
    """No usable mean is available — no current-season history, no consensus
    number, and no opportunity forecast. The caller has nothing to project.
    """

    def __init__(self, player_id: str, detail: str) -> None:
        self.player_id = player_id
        super().__init__(f"{player_id}: {detail}")


class ProjectionSource(StrEnum):
    """Where a projection's mean came from.

    ``PLAYER_HISTORY`` — the opportunity-model mean, with the player's own
    residual shape (blended toward the positional prior below the ≥4-game
    threshold). ``CONSENSUS_FALLBACK`` — the consensus-feed number, positional
    prior for the shape (rookies, role-change, no current-season history —
    methodology §3.7). ``OPPORTUNITY_FALLBACK`` — same as consensus fallback but
    no consensus number was supplied, so the opportunity mean stands in.
    """

    PLAYER_HISTORY = "player-history"
    CONSENSUS_FALLBACK = "consensus-fallback"
    OPPORTUNITY_FALLBACK = "opportunity-fallback"


@dataclass(frozen=True)
class ProjectionComponents:
    """Every intermediate behind a :class:`PlayerProjection`.

    ``source`` records where the mean came from (see :class:`ProjectionSource`).
    """

    source: ProjectionSource
    current_season_games: int
    mean_base: float
    opportunity_trend_slope: float
    opportunity_trend_multiplier: float
    matchup_factor: float
    matchup_factor_raw: float
    mean_final: float
    shape_own_weight: float
    residual_cv: float
    residual_skew: float


@dataclass(frozen=True)
class PlayerProjection:
    """One player's weekly point distribution.

    ``P10 < P50 < P90`` is a hard invariant (methodology §3.1) — enforced after
    rounding, so it holds even for a degenerate input. ``reasons`` lists why
    ``low_confidence`` is set; it is empty iff ``low_confidence`` is ``False``.
    """

    player_id: str
    position: str
    season: int
    week: int
    floor: float
    projection: float
    ceiling: float
    low_confidence: bool
    reasons: tuple[str, ...]
    components: ProjectionComponents


def project(
    history: PlayerHistory,
    opportunity: OpportunityMetrics | None,
    *,
    season: int,
    week: int,
    consensus_points: float | None = None,
    matchup: MatchupContext | None = None,
    params: ProjectionParams = DEFAULT_PARAMS,
    priors: Mapping[str, ResidualPrior] = POSITIONAL_RESIDUAL_PRIORS,
    rng_seed: int = 0,
) -> PlayerProjection:
    """Project ``history``'s player for ``(season, week)``.

    ``opportunity`` supplies the role-based mean (§3.2 step 1); pass ``None``
    only when relying on ``consensus_points``. ``consensus_points`` is the
    player's number from the consensus feed, already resolved by the caller —
    the fallback mean for rookies, role-change players, and players with no
    current-season history (§3.7). ``matchup`` drives the capped ±20% matchup
    factor (§3.5); ``None`` means an average matchup (×1.00).
    """
    cur_games = _current_season_games(history, season, week)
    n_games = len(cur_games)
    force_fallback = (
        n_games == 0 or history.is_rookie or history.role_change
    )

    mean_base, source = _resolve_mean_base(
        history.player_id, opportunity, consensus_points, force_fallback
    )

    trend_slope = _combined_usage_slope(cur_games, params)
    # Not clamped: methodology §3.4 leaves the opportunity adjustment uncapped
    # on purpose — it is bounded in practice by the [0, 1] range of the usage
    # shares the slope is measured on.
    trend_multiplier = 1.0 + params.opportunity_trend_sensitivity * trend_slope
    matchup_factor, matchup_factor_raw = _matchup_factor(
        matchup, params.matchup_adjustment_cap
    )
    mean_final = mean_base * trend_multiplier * matchup_factor

    positional_prior = prior_for_position(history.position, priors)
    if source is ProjectionSource.PLAYER_HISTORY:
        weights = decay_weights(n_games, params.decay_half_life_games)
        residuals = [g.actual_points - g.expected_points for g in cur_games]
        own_shape = own_residual_shape(
            residuals,
            weights,
            volume=mean_final,
            volume_floor=params.residual_volume_floor,
            skew_clamp=params.own_skew_clamp,
        )
        own_weight = min(n_games / params.own_shape_min_games, 1.0)
        shape = own_shape.blend(positional_prior, own_weight)
    else:
        own_weight = 0.0
        shape = positional_prior

    floor, projection, ceiling = _distribution_quantiles(
        mean_final, shape, params, rng_seed
    )

    reasons = _low_confidence_reasons(
        history, week, n_games, source, opportunity is None, params
    )
    components = ProjectionComponents(
        source=source,
        current_season_games=n_games,
        mean_base=mean_base,
        opportunity_trend_slope=trend_slope,
        opportunity_trend_multiplier=trend_multiplier,
        matchup_factor=matchup_factor,
        matchup_factor_raw=matchup_factor_raw,
        mean_final=mean_final,
        shape_own_weight=own_weight,
        residual_cv=shape.cv,
        residual_skew=shape.skew,
    )
    return PlayerProjection(
        player_id=history.player_id,
        position=history.position,
        season=season,
        week=week,
        floor=floor,
        projection=projection,
        ceiling=ceiling,
        low_confidence=bool(reasons),
        reasons=reasons,
        components=components,
    )


# --- mean assembly --------------------------------------------------------


def _current_season_games(
    history: PlayerHistory, season: int, week: int
) -> list[PlayerGame]:
    """Games this player has already played *this* season, oldest → newest.

    Same-or-later weeks are excluded so a projection never sees its own week or
    the future (methodology §3.6 counts current-season games only).
    """
    games = [
        g for g in history.games if g.season == season and g.week < week
    ]
    games.sort(key=lambda g: (g.season, g.week))
    return games


def _resolve_mean_base(
    player_id: str,
    opportunity: OpportunityMetrics | None,
    consensus_points: float | None,
    force_fallback: bool,
) -> tuple[float, ProjectionSource]:
    """Pick the pre-adjustment mean and label the source it came from."""
    if force_fallback:
        if consensus_points is not None:
            return consensus_points, ProjectionSource.CONSENSUS_FALLBACK
        if opportunity is not None:
            return opportunity.expected_points, ProjectionSource.OPPORTUNITY_FALLBACK
        raise InsufficientDataError(
            player_id,
            "no current-season history and neither a consensus nor an "
            "opportunity forecast to fall back on",
        )
    if opportunity is not None:
        return opportunity.expected_points, ProjectionSource.PLAYER_HISTORY
    if consensus_points is not None:
        # History exists but the opportunity model produced nothing this week;
        # lean on consensus for the mean while still using the player's shape.
        # ``opportunity is None`` on this path adds a low-confidence reason.
        return consensus_points, ProjectionSource.PLAYER_HISTORY
    raise InsufficientDataError(
        player_id, "current-season history present but no mean to anchor it"
    )


def _combined_usage_slope(
    cur_games: Sequence[PlayerGame], params: ProjectionParams
) -> float:
    """Weighted sum of the four usage signals' decay-weighted per-game slopes
    (§3.4). Needs at least two games carrying a usage snapshot.
    """
    usable = [g for g in cur_games if g.usage is not None]
    if len(usable) < 2:
        return 0.0
    weights = decay_weights(len(usable), params.decay_half_life_games)
    total = 0.0
    for field, weight in params.usage_weights().items():
        series = [getattr(g.usage, field) for g in usable]
        total += weight * weighted_slope(series, weights)
    return total


def _matchup_factor(
    matchup: MatchupContext | None, cap: float
) -> tuple[float, float]:
    """The clamped matchup factor and its pre-clamp value (§3.5).

    An absent matchup, or a non-positive league average, is an average matchup
    (×1.00). The clamped factor never leaves ``[1 - cap, 1 + cap]``.
    """
    if matchup is None:
        return 1.0, 1.0
    average = matchup.league_average_points_allowed_to_position
    if average <= 0.0:
        return 1.0, 1.0
    raw = matchup.opponent_points_allowed_to_position / average
    clamped = min(max(raw, 1.0 - cap), 1.0 + cap)
    return clamped, raw


# --- shape sampling -----------------------------------------------------


def _distribution_quantiles(
    mean_final: float,
    shape: ResidualPrior,
    params: ProjectionParams,
    rng_seed: int,
) -> tuple[float, float, float]:
    """Seeded Monte-Carlo P10 / P50 / P90 for a residual shape centred on
    ``mean_final``. Rounded half-up to two decimals like every other points
    figure in the app, then nudged if needed so the three are strictly
    increasing (methodology §3.1).
    """
    sigma = shape.cv * max(mean_final, params.residual_volume_floor)
    rng = random.Random(rng_seed)
    samples = [
        mean_final + _skewed_unit(rng, shape.skew) * sigma
        for _ in range(params.sample_count)
    ]
    samples.sort()

    floor = round_points(_quantile(samples, params.floor_quantile))
    projection = round_points(_quantile(samples, params.projection_quantile))
    ceiling = round_points(_quantile(samples, params.ceiling_quantile))

    gap = params.min_quantile_gap
    projection = max(projection, floor + gap)
    ceiling = max(ceiling, projection + gap)
    return floor, projection, ceiling


def _skewed_unit(rng: random.Random, skew: float) -> float:
    """A mean-0, ~unit-variance draw with Fisher skewness ≈ ``skew``.

    First-order Cornish-Fisher expansion of a standard normal: monotonic in
    ``z`` down to ``z = -3 / skew`` (below the reported P10 for the
    ``|skew| <= 1`` the model allows), so the sampled quantiles keep their
    order.
    """
    z = rng.gauss(0.0, 1.0)
    return z + (skew / 6.0) * (z * z - 1.0)


def _quantile(sorted_values: Sequence[float], p: float) -> float:
    """Linear-interpolation quantile (the ``numpy.quantile`` default method)."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("cannot take a quantile of an empty sample")
    if n == 1:
        return sorted_values[0]
    h = (n - 1) * p
    lo = math.floor(h)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


# --- low-confidence labelling -----------------------------------------


def _low_confidence_reasons(
    history: PlayerHistory,
    week: int,
    n_games: int,
    source: ProjectionSource,
    opportunity_missing: bool,
    params: ProjectionParams,
) -> tuple[str, ...]:
    """Every reason the projection is soft (methodology §3.6–§3.8).

    Empty tuple ⇒ full confidence.
    """
    reasons: list[str] = []
    if week <= params.early_season_week_max:
        reasons.append("weeks-1-3-prior-driven")
    if n_games < params.own_shape_min_games:
        reasons.append(f"only-{n_games}-current-season-games")
    if history.is_rookie:
        reasons.append("rookie")
    if history.role_change:
        reasons.append("role-change")
    if source in (
        ProjectionSource.CONSENSUS_FALLBACK,
        ProjectionSource.OPPORTUNITY_FALLBACK,
    ):
        reasons.append(str(source))
    elif opportunity_missing:
        # PLAYER_HISTORY path but the mean came from the consensus number
        # because the opportunity model produced nothing this week.
        reasons.append("no-opportunity-forecast")
    return tuple(reasons)
