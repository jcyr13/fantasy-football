from __future__ import annotations

import pytest

from deadparrots.strategy import expected_wins
from strategy_helpers import league

# methodology §4.2 — for each past week, the fraction of the other 11 teams
# Dead Parrots would have beaten; summed, then compared to actual wins.


def _week_scores(dp: float, others: list[float]) -> tuple[dict, dict]:
    return {"dp": dp}, {f"t{i:02d}": v for i, v in enumerate(others, start=1)}


def test_expected_wins_sums_weekly_beaten_fractions():
    # Week 1: DP 100 beats 5 of 11.  Week 2: DP 120 beats all 11.
    # Week 3: DP 100 beats 3, ties 1 (-> +0.5), loses 7.
    others = {
        "t01": [90.0, 90.0, 90.0],
        "t02": [90.0, 90.0, 90.0],
        "t03": [90.0, 90.0, 90.0],
        "t04": [95.0, 90.0, 100.0],  # week 3 tie
        "t05": [95.0, 90.0, 130.0],
        "t06": [110.0, 90.0, 130.0],
        "t07": [110.0, 90.0, 130.0],
        "t08": [110.0, 90.0, 130.0],
        "t09": [110.0, 90.0, 130.0],
        "t10": [110.0, 90.0, 130.0],
        "t11": [110.0, 90.0, 130.0],
    }
    state = league(
        dp_scores=[100.0, 120.0, 100.0],
        other_scores=others,
        dp_record=(2, 1, 0),
        current_week=8,
    )

    result = expected_wins(state)

    assert [w.week for w in result.weekly] == [1, 2, 3]
    assert result.weekly[0].opponents_beaten == pytest.approx(5.0)
    assert result.weekly[1].opponents_beaten == pytest.approx(11.0)
    assert result.weekly[2].opponents_beaten == pytest.approx(3.5)

    expected_total = 5 / 11 + 1.0 + 3.5 / 11
    assert result.expected_wins == pytest.approx(expected_total, abs=1e-4)
    assert result.weeks_counted == 3


def test_luck_is_actual_minus_expected():
    others = {f"t{i:02d}": [200.0] * 3 for i in range(1, 12)}  # DP beats nobody
    state = league(
        dp_scores=[80.0, 80.0, 80.0],
        other_scores=others,
        dp_record=(2, 1, 0),  # 2-1 despite being outscored every week
        current_week=8,
    )

    result = expected_wins(state)

    assert result.expected_wins == pytest.approx(0.0)
    assert result.actual_wins == 2.0
    assert result.luck == pytest.approx(2.0)  # the schedule has flattered the record


def test_actual_wins_counts_a_tie_as_a_half():
    others = {f"t{i:02d}": [1.0] * 2 for i in range(1, 12)}
    state = league(
        dp_scores=[100.0, 100.0], other_scores=others, dp_record=(1, 0, 1)
    )
    assert expected_wins(state).actual_wins == 1.5


def test_weeks_without_a_dead_parrots_score_are_skipped():
    others = {f"t{i:02d}": {1: 90.0, 2: 90.0} for i in range(1, 12)}
    state = league(
        dp_scores={1: 100.0},  # only week 1 played for DP
        other_scores=others,
        current_week=3,
    )
    result = expected_wins(state)
    assert result.weeks_counted == 1
    assert result.weekly[0].week == 1
