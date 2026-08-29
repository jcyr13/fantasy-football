from __future__ import annotations

from dataclasses import replace

import pytest

from deadparrots.strategy import StrategyParams, playoff_odds
from strategy_helpers import league

# methodology §4.3 — playoff odds from a season-rest simulation that plays the
# remaining schedule out over per-team weekly marginals.

FAST = StrategyParams(playoff_sim_trials=2_000, playoff_sim_seed=735806)


def _state(dp_mean: float, other_mean: float = 100.0, **kw):
    return league(
        dp_scores=[100.0] * 7,
        dp_forecast_mean=dp_mean,
        other_forecast_mean=other_mean,
        remaining_weeks=[8, 9, 10, 11, 12, 13, 14],
        current_week=8,
        **kw,
    )


def test_odds_are_a_probability_and_the_league_sums_to_the_seed_count():
    result = playoff_odds(_state(100.0), FAST)

    assert result.trials == 2_000
    assert all(0.0 <= t.playoff_odds <= 1.0 for t in result.by_team)
    # exactly ``playoff_team_count`` teams make it every trial
    assert sum(t.playoff_odds for t in result.by_team) == pytest.approx(6.0, abs=0.02)


def test_a_stronger_forecast_can_only_raise_playoff_odds():
    weak = playoff_odds(_state(80.0), FAST).dead_parrots_odds
    even = playoff_odds(_state(100.0), FAST).dead_parrots_odds
    strong = playoff_odds(_state(130.0), FAST).dead_parrots_odds

    assert weak < even < strong
    assert strong > 0.9
    assert weak < 0.2


def test_identical_state_and_seed_give_identical_odds():
    a = playoff_odds(_state(105.0), FAST)
    b = playoff_odds(_state(105.0), FAST)
    assert a.by_team == b.by_team


def test_a_different_seed_moves_the_estimate_but_not_the_verdict():
    seed_a = playoff_odds(_state(100.0), FAST).dead_parrots_odds
    seed_b = playoff_odds(
        _state(100.0), replace(FAST, playoff_sim_seed=999)
    ).dead_parrots_odds
    assert seed_a != seed_b
    assert abs(seed_a - seed_b) < 0.1  # Monte-Carlo noise, not a different story


def test_current_record_carries_into_the_simulation():
    # Bank a big win lead; even an even forecast should make the playoffs often.
    ahead = _state(100.0, dp_record=(7, 0, 0))
    behind = _state(100.0, dp_record=(0, 7, 0))
    assert (
        playoff_odds(ahead, FAST).dead_parrots_odds
        > playoff_odds(behind, FAST).dead_parrots_odds
    )


def test_missing_forecast_for_a_scheduled_team_raises():
    state = _state(100.0)
    trimmed = replace(
        state,
        scoring_forecasts=tuple(
            f for f in state.scoring_forecasts if f.team_id != "t05"
        ),
    )
    with pytest.raises(ValueError, match="t05"):
        playoff_odds(trimmed, FAST)
