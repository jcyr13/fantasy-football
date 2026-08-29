"""RIP TIDE scoring engine.

``score_player_weeks(rows, ruleset)`` is a pure function — no I/O — turning
counting stats into fantasy points for offense, kickers, and team defense under
the exact RIP TIDE rules (``RIP_TIDE_RULESET``). Nothing in the app is built on
its output until it reproduces real 2025 Yahoo actuals exactly; that gate lives
in ``tests/test_scoring_gate.py`` and its capture tool in ``scoring.oracle``.
"""

from __future__ import annotations

from .engine import round_points, score_player_weeks, score_row, total_points
from .rows import (
    INDIVIDUAL_DEFENSE_STATS,
    KICKER_STATS,
    OFFENSE_STATS,
    TEAM_DEFENSE_STATS,
    PlayerWeekKey,
    ScoredPlayerWeek,
    ScoringUnit,
    StatRow,
    UnknownStatError,
)
from .ruleset import (
    RIP_TIDE_RULESET,
    IndividualDefenseRules,
    KickerRules,
    LeagueRuleset,
    OffenseRules,
    PointsAllowedTier,
    TeamDefenseRules,
)

__all__ = [
    "INDIVIDUAL_DEFENSE_STATS",
    "KICKER_STATS",
    "OFFENSE_STATS",
    "RIP_TIDE_RULESET",
    "TEAM_DEFENSE_STATS",
    "IndividualDefenseRules",
    "KickerRules",
    "LeagueRuleset",
    "OffenseRules",
    "PlayerWeekKey",
    "PointsAllowedTier",
    "ScoredPlayerWeek",
    "ScoringUnit",
    "StatRow",
    "TeamDefenseRules",
    "UnknownStatError",
    "round_points",
    "score_player_weeks",
    "score_row",
    "total_points",
]
