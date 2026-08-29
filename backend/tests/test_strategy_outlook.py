from __future__ import annotations

import pytest

from deadparrots.simulation import seed_from_snapshot_id
from deadparrots.strategy import (
    LeagueState,
    StrategyParams,
    TeamScoringForecast,
    team_outlook,
)
from strategy_helpers import full_roster, league

# Issue #12 acceptance criterion 5: fed a hand-built fixture league state, all
# thresholds and grades assert correctly. One coherent "contend" fixture drives
# every layer at once.

FAST = StrategyParams(playoff_sim_trials=3_000, playoff_sim_seed=42)


def _contender() -> LeagueState:
    # DP scores a flat 120 across weeks 1-7. Four teams outscore it (130), the
    # other seven trail (90): DP sits at the 7/11 ~= 63.6th points-for
    # percentile — above the 60th contend line.
    others = {f"t{i:02d}": [130.0] * 7 for i in range(1, 5)}
    others.update({f"t{i:02d}": [90.0] * 7 for i in range(5, 12)})

    state = league(
        dp_scores=[120.0] * 7,
        other_scores=others,
        dp_record=(5, 2, 0),
        current_week=8,
        remaining_weeks=[8, 9, 10, 11, 12, 13, 14],
        roster=full_roster(qb=1, byes={"wr1": 9, "wr2": 9, "qb1": 11}),
        regular_season_weeks=14,
    )
    # Forecasts: DP and the four strong teams project ~125/wk, the rest ~95.
    strong = {"dp"} | {f"t{i:02d}" for i in range(1, 5)}
    forecasts = tuple(
        TeamScoringForecast(
            team_id=f.team_id,
            mean=125.0 if f.team_id in strong else 95.0,
            sigma=18.0,
        )
        for f in state.scoring_forecasts
    )
    from dataclasses import replace

    return replace(state, scoring_forecasts=forecasts)


def test_team_strength_is_a_points_for_percentile_not_a_record():
    outlook = team_outlook(_contender(), params=FAST)
    ts = outlook.team_strength

    assert ts.decay_weighted_points_for == pytest.approx(120.0)
    assert ts.percentile == pytest.approx(100.0 * 7 / 11, abs=1e-4)
    assert ts.percentile >= FAST.contend_points_for_percentile
    assert len(ts.league) == 12


def test_expected_wins_is_shown_against_actual_wins():
    outlook = team_outlook(_contender(), params=FAST)
    ew = outlook.expected_wins

    # 120 beats 7 of 11 every week, over 7 completed weeks
    assert ew.expected_wins == pytest.approx(7 * (7 / 11), abs=1e-4)
    assert ew.actual_wins == 5.0
    assert ew.luck == pytest.approx(5.0 - 7 * (7 / 11), abs=1e-4)


def test_contend_signal_fires_with_its_inputs_and_recommends_nothing():
    outlook = team_outlook(_contender(), params=FAST)
    sig = outlook.signal

    assert sig.signal == "contend"
    assert sig.points_for_percentile == outlook.team_strength.percentile
    assert sig.playoff_odds == outlook.playoff_odds.dead_parrots_odds
    assert sig.playoff_odds >= FAST.striking_distance_playoff_odds
    assert sig.contend_percentile_threshold == 60.0
    assert sig.recommends_transaction is False
    assert sig.rationale


def test_bye_crunch_grades_each_upcoming_week():
    outlook = team_outlook(_contender(), params=FAST)
    grades = {w.week: w.grade for w in outlook.bye_crunch.weeks}

    assert set(grades) == {8, 9, 10, 11, 12, 13, 14}
    assert grades[9] == "warn"  # wr1 + wr2 on bye
    assert grades[11] == "critical"  # lone QB on bye -> unfieldable
    assert grades[8] == grades[10] == grades[12] == "ok"
    assert outlook.bye_crunch.week(11).can_field_legal_lineup is False


def test_before_week_five_the_signal_is_too_early():
    state = _contender()
    from dataclasses import replace

    early = replace(state, current_week=3)
    assert team_outlook(early, params=FAST).signal.signal == "too-early"


def test_playoff_sim_seed_override_makes_the_outlook_reproducible():
    state = _contender()
    seed = seed_from_snapshot_id("2026-W08")
    a = team_outlook(state, params=FAST, playoff_sim_seed=seed)
    b = team_outlook(state, params=FAST, playoff_sim_seed=seed)

    assert a.playoff_odds.by_team == b.playoff_odds.by_team
    assert a.playoff_odds.rng_seed == seed


def test_a_weak_rebuild_fixture_flips_every_signal():
    others = {f"t{i:02d}": [130.0] * 7 for i in range(1, 12)}  # everyone outscores DP
    state = league(
        dp_scores=[80.0] * 7,
        other_scores=others,
        dp_record=(1, 6, 0),
        current_week=9,
        remaining_weeks=[9, 10, 11, 12, 13, 14],
        dp_forecast_mean=80.0,
        other_forecast_mean=125.0,
    )
    outlook = team_outlook(state, params=FAST)

    assert outlook.team_strength.percentile <= FAST.rebuild_points_for_percentile
    assert outlook.playoff_odds.dead_parrots_odds <= FAST.low_playoff_odds
    assert outlook.signal.signal == "rebuild"
    assert outlook.signal.recommends_transaction is False
