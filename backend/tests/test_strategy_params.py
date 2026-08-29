from __future__ import annotations

import pytest

from deadparrots.strategy import DEFAULT_STRATEGY_PARAMS, StrategyParams

# Pin the methodology §5 (rows 6–10) defaults so a drift from the signed-off
# ``docs/methodology.md`` fails CI, the same guard ``test_projection_params.py``
# puts on the projection model.


def test_defaults_match_methodology_section_5():
    p = DEFAULT_STRATEGY_PARAMS
    assert p.team_strength_decay_half_life_weeks == 4.0  # row 6
    assert p.contend_points_for_percentile == 60.0  # row 7
    assert p.rebuild_points_for_percentile == 35.0  # row 8
    assert p.contend_signal_start_week == 5  # row 9
    assert (p.bye_crunch_warn_count, p.bye_crunch_critical_count) == (2, 3)  # row 10


def test_striking_distance_and_low_odds_are_a_playoff_odds_floor():
    # methodology §6 Q3 resolved to a playoff-odds floor (ADR-0009)
    p = DEFAULT_STRATEGY_PARAMS
    assert 0.0 < p.low_playoff_odds < p.striking_distance_playoff_odds < 1.0


def test_playoff_sim_is_seeded_and_ten_thousand_trials():
    p = DEFAULT_STRATEGY_PARAMS
    assert p.playoff_sim_trials == 10_000
    assert p.playoff_sim_seed == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rebuild_points_for_percentile": 70.0, "contend_points_for_percentile": 60.0},
        {"low_playoff_odds": 0.9, "striking_distance_playoff_odds": 0.25},
        {"bye_crunch_warn_count": 0},
        {"bye_crunch_critical_count": 2, "bye_crunch_warn_count": 2},
        {"playoff_sim_trials": 0},
    ],
)
def test_incoherent_params_raise(kwargs):
    with pytest.raises(ValueError):
        StrategyParams(**kwargs)
