"""RIP TIDE lineup optimizer (issue #11; ADR-0002, ADR-0008).

``optimize_lineups(roster, opponent, rng_seed=...)`` enumerates every legal
lineup from the non-IR roster under the RIP TIDE slot rules (QB, 2×RB, 2×WR, TE,
W/R/T flex, K, DEF, D), scores each against the opponent's likely lineup with
the head-to-head Monte Carlo under common random numbers, and returns the
max-P(win) lineup (the primary recommendation) alongside the max-EV, floor, and
ceiling lineups, the favored→floor / underdog→ceiling threshold-rule
alternative (a toggle, never the default), the per-slot gap-driver
decomposition, and the opponent's swing-player ranking.

``build_opponent_lineup`` assembles the opponent's likely starters — their
Yahoo-set lineup when it is complete and legal, else a prior-week or
projection-based heuristic — and records which assumption was used.
"""

from __future__ import annotations

from .evaluate import (
    ContributionSampler,
    LineupEvaluation,
    evaluate_lineups,
    sum_contributions,
)
from .gap_drivers import GapDriver, gap_drivers, total_expected_gap
from .opponent import (
    DEFAULT_MAX_OBVIOUS_UPGRADES,
    DEFAULT_UPGRADE_MARGIN,
    OpponentAssumption,
    OpponentLineup,
    build_opponent_lineup,
)
from .optimize import (
    DEFAULT_FAVORED_THRESHOLD,
    DEFAULT_UNDERDOG_THRESHOLD,
    OptimizerResult,
    RecommendationEngine,
    ThresholdRuleRecommendation,
    optimize_lineups,
)
from .roster import Lineup, RosterPlayer, enumerate_lineups
from .slots import (
    RIP_TIDE_SLOTS,
    HasPosition,
    LineupSlots,
    SlotRule,
    assign_slots,
    is_legal_lineup,
    role_of,
)
from .swing import SwingPlayer, swing_players

__all__ = [
    "DEFAULT_FAVORED_THRESHOLD",
    "DEFAULT_MAX_OBVIOUS_UPGRADES",
    "DEFAULT_UNDERDOG_THRESHOLD",
    "DEFAULT_UPGRADE_MARGIN",
    "RIP_TIDE_SLOTS",
    "ContributionSampler",
    "GapDriver",
    "HasPosition",
    "Lineup",
    "LineupEvaluation",
    "LineupSlots",
    "OpponentAssumption",
    "OpponentLineup",
    "OptimizerResult",
    "RecommendationEngine",
    "RosterPlayer",
    "SlotRule",
    "SwingPlayer",
    "ThresholdRuleRecommendation",
    "assign_slots",
    "build_opponent_lineup",
    "enumerate_lineups",
    "evaluate_lineups",
    "gap_drivers",
    "is_legal_lineup",
    "optimize_lineups",
    "role_of",
    "sum_contributions",
    "swing_players",
    "total_expected_gap",
]
