"""Shared builders for the projection regression fixtures.

Both the fixture generator (``scripts/gen_projection_fixtures`` — run by hand
when the model deliberately changes) and ``test_projection_regression.py``
import ``CASES`` and ``build_inputs`` from here, so the scenario definitions
live in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deadparrots.projection import (
    MatchupContext,
    OpportunityMetrics,
    PlayerGame,
    PlayerHistory,
    UsageSnapshot,
)


@dataclass(frozen=True)
class Case:
    name: str
    season: int
    week: int
    rng_seed: int
    history: PlayerHistory
    opportunity: OpportunityMetrics | None
    consensus_points: float | None = None
    matchup: MatchupContext | None = None


def _u(snap: float, tgt: float, route: float, rz: float) -> UsageSnapshot:
    return UsageSnapshot(snap, tgt, route, rz)


def _season_games(
    season: int,
    weeks: int,
    *,
    actual: list[float],
    expected: float,
    usage: list[UsageSnapshot] | None = None,
) -> tuple[PlayerGame, ...]:
    return tuple(
        PlayerGame(
            season=season,
            week=w,
            actual_points=actual[w - 1],
            expected_points=expected,
            usage=usage[w - 1] if usage is not None else None,
        )
        for w in range(1, weeks + 1)
    )


# --- the scenarios --------------------------------------------------------

_VET_WR_USAGE = [
    _u(0.78, 0.24, 0.86, 0.14),
    _u(0.80, 0.26, 0.88, 0.16),
    _u(0.82, 0.25, 0.90, 0.12),
    _u(0.85, 0.28, 0.91, 0.18),
    _u(0.86, 0.30, 0.92, 0.20),
    _u(0.88, 0.31, 0.93, 0.19),
    _u(0.90, 0.33, 0.94, 0.22),
]

CASES: tuple[Case, ...] = (
    Case(
        name="veteran_wr_rising_usage_tough_matchup",
        season=2026,
        week=9,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-veteran-wr",
            position="WR",
            games=_season_games(
                2026,
                7,
                actual=[11.4, 18.9, 7.2, 22.1, 14.6, 9.8, 25.3],
                expected=14.0,
                usage=_VET_WR_USAGE,
            ),
        ),
        opportunity=OpportunityMetrics(expected_points=15.5),
        consensus_points=14.2,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=33.0,
            league_average_points_allowed_to_position=25.0,
        ),
    ),
    Case(
        name="thin_history_rb_two_games_blended",
        season=2026,
        week=6,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-thin-rb",
            position="RB",
            games=_season_games(
                2026,
                2,
                actual=[6.1, 19.7],
                expected=11.0,
                usage=[_u(0.44, 0.08, 0.40, 0.22), _u(0.61, 0.11, 0.55, 0.35)],
            ),
        ),
        opportunity=OpportunityMetrics(expected_points=12.5),
        consensus_points=10.8,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=19.0,
            league_average_points_allowed_to_position=20.0,
        ),
    ),
    Case(
        name="rookie_wr_consensus_fallback",
        season=2026,
        week=7,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-rookie-wr",
            position="WR",
            games=(),
            is_rookie=True,
        ),
        opportunity=None,
        consensus_points=8.4,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=27.0,
            league_average_points_allowed_to_position=25.0,
        ),
    ),
    Case(
        name="role_change_te_full_history_still_fallback",
        season=2026,
        week=11,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-role-change-te",
            position="TE",
            games=_season_games(
                2026,
                9,
                actual=[3.1, 5.4, 2.8, 9.9, 4.2, 6.7, 12.1, 3.5, 8.0],
                expected=6.0,
                usage=[_u(0.55, 0.12, 0.50, 0.10)] * 9,
            ),
            role_change=True,
        ),
        opportunity=OpportunityMetrics(expected_points=9.0),
        consensus_points=7.5,
        matchup=None,
    ),
    Case(
        name="week2_early_season_prior_driven",
        season=2026,
        week=2,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-early-qb",
            position="QB",
            games=(
                _season_games(
                    2025,
                    17,
                    actual=[float(18 + (w % 5) * 3) for w in range(1, 18)],
                    expected=21.0,
                )
                + _season_games(
                    2026,
                    1,
                    actual=[24.6],
                    expected=21.0,
                )
            ),
        ),
        opportunity=OpportunityMetrics(expected_points=22.0),
        consensus_points=21.4,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=18.0,
            league_average_points_allowed_to_position=20.0,
        ),
    ),
    Case(
        name="matchup_cap_clamped_shutout_defense",
        season=2026,
        week=10,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-capped-rb",
            position="RB",
            games=_season_games(
                2026,
                8,
                actual=[12.0, 8.5, 15.2, 10.1, 18.9, 7.7, 14.3, 11.0],
                expected=12.0,
                usage=[_u(0.70, 0.10, 0.30, 0.40)] * 8,
            ),
        ),
        opportunity=OpportunityMetrics(expected_points=13.0),
        consensus_points=12.0,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=6.0,
            league_average_points_allowed_to_position=20.0,
        ),
    ),
    Case(
        name="idp_linebacker_full_history",
        season=2026,
        week=12,
        rng_seed=735806,
        history=PlayerHistory(
            player_id="00-idp-lb",
            position="LB",
            games=_season_games(
                2026,
                10,
                actual=[9.5, 14.0, 7.0, 11.5, 18.0, 6.5, 12.0, 10.0, 15.5, 8.0],
                expected=11.0,
                usage=[_u(0.98, 0.0, 0.0, 0.0)] * 10,
            ),
        ),
        opportunity=OpportunityMetrics(expected_points=11.5),
        consensus_points=10.5,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=13.0,
            league_average_points_allowed_to_position=11.0,
        ),
    ),
)


def case_by_name(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(name)


def expected_payload(case: Case) -> dict[str, Any]:
    """Run ``project`` for a case and shape the result for the fixture file."""
    from deadparrots.projection import project

    p = project(
        case.history,
        case.opportunity,
        season=case.season,
        week=case.week,
        consensus_points=case.consensus_points,
        matchup=case.matchup,
        rng_seed=case.rng_seed,
    )
    c = p.components
    return {
        "floor": p.floor,
        "projection": p.projection,
        "ceiling": p.ceiling,
        "low_confidence": p.low_confidence,
        "reasons": list(p.reasons),
        "components": {
            "source": c.source,
            "current_season_games": c.current_season_games,
            "mean_base": c.mean_base,
            "opportunity_trend_slope": c.opportunity_trend_slope,
            "opportunity_trend_multiplier": c.opportunity_trend_multiplier,
            "matchup_factor": c.matchup_factor,
            "matchup_factor_raw": c.matchup_factor_raw,
            "mean_final": c.mean_final,
            "shape_own_weight": c.shape_own_weight,
            "residual_cv": c.residual_cv,
            "residual_skew": c.residual_skew,
        },
    }
