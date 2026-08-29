"""Assembled weekly view (issue #16; ADR-0013).

``assemble_week(...)`` is the one adapter from raw nflverse frames + normalized
Yahoo objects to a frozen :class:`AssembledWeek` — the reconciliation point the
projection-input, optimizer and three strategic-layer ADRs (0006, 0008–0011)
each deferred here. ``build_weekly_view`` and ``compute_lineup_lab`` compose the
pure layers over it for the API.

Where v1's pulls are too thin for a layer's real input (the projection
opportunity baseline, league-wide weekly history, the full desperate-team
rosters) the assembly approximates and names each approximation in
``AssembledWeek.caveats``.
"""

from __future__ import annotations

from .assemble import WEEKLY_FORECAST_SIGMA_FRACTION, assemble_week
from .identity import PlayerResolver, ResolvedPlayer, normalize_name, synthetic_id
from .inputs import AssembledPlayer, AssembledWeek
from .opportunity import player_games, target_week_opportunity, usage_by_player_week
from .scored_history import (
    ScoredGame,
    scored_games_by_player,
    stat_rows_from_player_stats,
)
from .view import (
    LineupLabResult,
    WeeklyView,
    auto_fill_lineups,
    build_opponent,
    build_weekly_view,
    compute_lineup_lab,
)

__all__ = [
    "WEEKLY_FORECAST_SIGMA_FRACTION",
    "AssembledPlayer",
    "AssembledWeek",
    "LineupLabResult",
    "PlayerResolver",
    "ResolvedPlayer",
    "ScoredGame",
    "WeeklyView",
    "assemble_week",
    "auto_fill_lineups",
    "build_opponent",
    "build_weekly_view",
    "compute_lineup_lab",
    "normalize_name",
    "player_games",
    "scored_games_by_player",
    "stat_rows_from_player_stats",
    "synthetic_id",
    "target_week_opportunity",
    "usage_by_player_week",
]
