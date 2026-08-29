"""RIP TIDE projection model (issue #9; methodology §3).

``project(history, opportunity, ...)`` is a pure, seeded function turning a
player's scored history, an opportunity-model mean, an optional matchup, and an
optional consensus number into a weekly RIP TIDE point distribution summarised
as floor (P10) / projection (P50) / ceiling (P90). The mean comes from the
opportunity model; the shape comes from position-level historical residuals,
blended toward the player's own residuals once they have ≥4 games this season.
Rookies, role-change players, thin histories, and Weeks 1–3 are flagged
low-confidence.

Every tunable is in :class:`ProjectionParams`, transcribed from the signed-off
``docs/methodology.md``.
"""

from __future__ import annotations

from .decay import (
    decay_weights,
    per_game_decay,
    weighted_mean,
    weighted_skew,
    weighted_slope,
    weighted_std,
)
from .inputs import (
    MatchupContext,
    OpportunityMetrics,
    PlayerGame,
    PlayerHistory,
    UsageSnapshot,
)
from .model import (
    InsufficientDataError,
    PlayerProjection,
    ProjectionComponents,
    ProjectionError,
    project,
)
from .params import DEFAULT_PARAMS, ProjectionParams
from .residuals import (
    POSITIONAL_RESIDUAL_PRIORS,
    ResidualPrior,
    UnknownPositionError,
    own_residual_shape,
    prior_for_position,
)

__all__ = [
    "DEFAULT_PARAMS",
    "POSITIONAL_RESIDUAL_PRIORS",
    "InsufficientDataError",
    "MatchupContext",
    "OpportunityMetrics",
    "PlayerGame",
    "PlayerHistory",
    "PlayerProjection",
    "ProjectionComponents",
    "ProjectionError",
    "ProjectionParams",
    "ResidualPrior",
    "UnknownPositionError",
    "UsageSnapshot",
    "decay_weights",
    "own_residual_shape",
    "per_game_decay",
    "prior_for_position",
    "project",
    "weighted_mean",
    "weighted_skew",
    "weighted_slope",
    "weighted_std",
]
