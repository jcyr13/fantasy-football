from __future__ import annotations

import dataclasses

import pytest

from deadparrots.trade import DEFAULT_TRADE_PARAMS, TradeParams

# Issue #13 / methodology §4.5–§4.9 and §6 review answers ("accepted as
# documented"). Each assertion cites the section it pins.


def test_usage_signals_are_equal_weighted():
    # methodology §4.5 / §6 Q6 — equal weights on the four usage signals
    weights = DEFAULT_TRADE_PARAMS.usage_weights()
    assert set(weights) == {
        "snap_share",
        "target_share",
        "route_participation",
        "red_zone_share",
    }
    assert list(weights.values()) == [0.25, 0.25, 0.25, 0.25]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_opportunity_decay_matches_projection_window():
    # methodology §4.5 ("same signals as §3.4") / §5 row 1 — 4-game half-life
    assert DEFAULT_TRADE_PARAMS.opportunity_decay_half_life_games == 4.0


def test_edge_tier_is_twelve_at_rb_wr_and_six_at_qb_te():
    # methodology §4.8 / §6 Q4 — "edge ≥ 12 ranks at RB/WR, ≥ 6 at QB/TE"
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("RB") == 12
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("WR") == 12
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("QB") == 6
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("TE") == 6
    # shallow roster positions take the same full-tier gap as QB/TE
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("K") == 6
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("DEF") == 6
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("IDP") == 6
    # an unexpected role spelling falls back to the full-tier default
    assert DEFAULT_TRADE_PARAMS.edge_tier_for("PUNTER") == 6


def test_desperate_team_components_are_equally_weighted():
    # methodology §4.9 / §6 Q5 — four equally-weighted components
    weights = [
        DEFAULT_TRADE_PARAMS.desperate_weight_record,
        DEFAULT_TRADE_PARAMS.desperate_weight_points_for,
        DEFAULT_TRADE_PARAMS.desperate_weight_roster_age,
        DEFAULT_TRADE_PARAMS.desperate_weight_bye_crunch,
    ]
    assert weights == [0.25, 0.25, 0.25, 0.25]
    assert sum(weights) == pytest.approx(1.0)


def test_surfaces_top_two_to_three_desperate_teams():
    # methodology §4.9 — "surface the top 2–3"
    assert DEFAULT_TRADE_PARAMS.desperate_surface_count == 3


def test_trade_deadline_is_november_28():
    # issue #13 — "a countdown to November 28"
    assert (
        DEFAULT_TRADE_PARAMS.trade_deadline_month,
        DEFAULT_TRADE_PARAMS.trade_deadline_day,
    ) == (11, 28)


def test_params_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_TRADE_PARAMS.opportunity_up_slope = 0.5  # type: ignore[misc]


def test_params_are_overridable_via_replace():
    tuned = dataclasses.replace(TradeParams(), output_spike_slope=3.0)
    assert tuned.output_spike_slope == 3.0
    assert DEFAULT_TRADE_PARAMS.output_spike_slope == 1.5


def test_weight_sums_are_validated():
    with pytest.raises(ValueError, match="usage weights"):
        TradeParams(usage_weight_snap_share=0.9)
    with pytest.raises(ValueError, match="desperate-team weights"):
        TradeParams(desperate_weight_record=0.9)


def test_slope_ordering_is_validated():
    with pytest.raises(ValueError, match="opportunity_flat_slope"):
        TradeParams(opportunity_flat_slope=0.2, opportunity_up_slope=0.1)
    with pytest.raises(ValueError, match="output_lag_slope"):
        TradeParams(output_lag_slope=5.0, output_spike_slope=1.0)
