"""Pin the assembled-view placeholder magnitudes (ADR-0013 §4) so a tuning
change is a deliberate edit here, not a silent drift — the same treatment
`test_strategy_params.py` gives the strategy knobs."""

from __future__ import annotations

from deadparrots.weekly import assemble as A


def test_placeholder_magnitudes_are_pinned():
    assert A.WEEKLY_FORECAST_SIGMA_FRACTION == 0.18
    assert A.NOMINAL_REPLACEMENT_POINTS == 1.0
    assert A.REGULAR_SEASON_WEEKS == 14
    assert A.PLAYOFF_TEAM_COUNT == 6


def test_forecast_sigma_is_a_nonnegative_fraction():
    assert 0.0 < A.WEEKLY_FORECAST_SIGMA_FRACTION < 1.0
