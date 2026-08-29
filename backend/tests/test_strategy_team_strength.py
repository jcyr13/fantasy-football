from __future__ import annotations

import pytest

from deadparrots.projection import decay_weights, weighted_mean
from deadparrots.strategy import StrategyParams, team_strength
from strategy_helpers import league

# methodology §4.1 — decay-weighted rolling points-for as a league percentile
# against the other 11, never win/loss record.


def test_percentile_is_share_of_other_eleven_below_dead_parrots():
    # 4 of the 11 others sit below Dead Parrots' 100, 7 above.
    others = {f"t{i:02d}": [80.0] * 3 for i in range(1, 5)}
    others.update({f"t{i:02d}": [120.0] * 3 for i in range(5, 12)})
    state = league(dp_scores=[100.0, 100.0, 100.0], other_scores=others, current_week=8)

    result = team_strength(state)

    assert result.percentile == pytest.approx(100.0 * 4 / 11, abs=1e-2)
    assert result.weeks_counted == 3
    assert result.dead_parrots_rank == 8  # 7 teams ahead


def test_ties_count_as_half_a_team():
    others = {f"t{i:02d}": [100.0] * 2 for i in range(1, 12)}  # all exactly equal
    state = league(dp_scores=[100.0, 100.0], other_scores=others)

    assert team_strength(state).percentile == pytest.approx(50.0)


def test_record_is_ignored_only_points_for_moves_the_needle():
    strong_scores = {f"t{i:02d}": [90.0] * 3 for i in range(1, 12)}
    losing_but_high = league(
        dp_scores=[130.0, 130.0, 130.0],
        other_scores=strong_scores,
        dp_record=(0, 3, 0),  # 0-3 on the season
        current_week=8,
    )
    assert team_strength(losing_but_high).percentile == 100.0


def test_decay_weighting_rewards_recent_scoring():
    # Same three weekly totals, opposite order: the improving team is stronger.
    improving = league(dp_scores=[80.0, 100.0, 140.0], current_week=8)
    fading = league(dp_scores=[140.0, 100.0, 80.0], current_week=8)

    assert (
        team_strength(improving).decay_weighted_points_for
        > team_strength(fading).decay_weighted_points_for
    )


def test_decay_weighted_value_matches_the_methodology_formula():
    series = [80.0, 100.0, 140.0]
    state = league(dp_scores=series, current_week=8)
    params = StrategyParams()

    expected = weighted_mean(
        series, decay_weights(len(series), params.team_strength_decay_half_life_weeks)
    )
    assert team_strength(state, params).decay_weighted_points_for == pytest.approx(
        expected, abs=1e-2
    )


def test_league_table_is_ranked_and_carries_every_team():
    state = league(dp_scores=[100.0, 100.0], current_week=6)
    result = team_strength(state)

    assert len(result.league) == 12
    values = [v.decay_weighted_points_for for v in result.league]
    assert values == sorted(values, reverse=True)
    assert [v.rank for v in result.league] == list(range(1, 13))
    assert sum(v.is_dead_parrots for v in result.league) == 1
