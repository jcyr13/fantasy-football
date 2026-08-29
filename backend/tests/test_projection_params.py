from __future__ import annotations

import dataclasses

import pytest

from deadparrots.projection import DEFAULT_PARAMS, ProjectionParams

# Acceptance criterion 7 of issue #9: "Parameters match the signed-off
# docs/methodology.md." Each assertion below cites the section / §5 row it pins.


def test_decay_half_life_is_four_games():
    # methodology §3.3 and §5 row 1
    assert DEFAULT_PARAMS.decay_half_life_games == 4.0


def test_matchup_cap_is_twenty_percent():
    # methodology §3.5 and §5 row 2 — "clamped to [0.80, 1.20]"
    assert DEFAULT_PARAMS.matchup_adjustment_cap == 0.20


def test_own_shape_threshold_is_four_current_season_games():
    # methodology §3.6 and §5 row 3
    assert DEFAULT_PARAMS.own_shape_min_games == 4


def test_thin_history_blend_is_linear_games_over_four():
    # methodology §3.6 / §5 row 4 — w = games/4, so 0 -> 0, 3 -> 0.75, 4 -> 1
    n = DEFAULT_PARAMS.own_shape_min_games
    assert [min(g / n, 1.0) for g in (0, 1, 2, 3, 4, 5)] == [0.0, 0.25, 0.5, 0.75, 1.0, 1.0]


def test_early_season_label_window_is_weeks_1_to_3():
    # methodology §3.8 and §5 row 5
    assert DEFAULT_PARAMS.early_season_week_max == 3


def test_usage_signals_are_equal_weighted():
    # methodology §3.4 / §4.5 open question 6 — equal weights on the four signals
    weights = DEFAULT_PARAMS.usage_weights()
    assert set(weights) == {
        "snap_share",
        "target_share",
        "route_participation",
        "red_zone_share",
    }
    assert list(weights.values()) == [0.25, 0.25, 0.25, 0.25]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_reported_quantiles_are_p10_p50_p90():
    # methodology §3.1
    assert (
        DEFAULT_PARAMS.floor_quantile,
        DEFAULT_PARAMS.projection_quantile,
        DEFAULT_PARAMS.ceiling_quantile,
    ) == (0.10, 0.50, 0.90)


def test_params_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_PARAMS.decay_half_life_games = 2.0  # type: ignore[misc]


def test_params_are_overridable_via_replace():
    tuned = dataclasses.replace(ProjectionParams(), decay_half_life_games=3.0)
    assert tuned.decay_half_life_games == 3.0
    assert DEFAULT_PARAMS.decay_half_life_games == 4.0
