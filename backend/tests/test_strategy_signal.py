from __future__ import annotations

import pytest

from deadparrots.strategy import ContendRebuildHold, StrategyParams, contend_rebuild_hold
from strategy_helpers import odds_stub, strength_stub

# methodology §4.3 — contend / rebuild / hold from the team-strength percentile
# and season-rest playoff odds, from ~Week 5, recommending no transaction.

PARAMS = StrategyParams()


def _signal(percentile: float, odds: float, *, week: int = 8) -> ContendRebuildHold:
    return contend_rebuild_hold(
        strength_stub(percentile), odds_stub(odds), week=week, params=PARAMS
    )


def test_before_week_five_the_signal_is_withheld_but_inputs_are_shown():
    result = _signal(90.0, 0.9, week=4)
    assert result.signal == "too-early"
    assert result.points_for_percentile == 90.0
    assert result.playoff_odds == 0.9
    assert result.recommends_transaction is False


def test_contend_needs_both_a_high_percentile_and_striking_distance_odds():
    assert _signal(65.0, 0.40).signal == "contend"
    # percentile clears 60 but odds below the 0.25 striking-distance floor
    assert _signal(65.0, 0.10).signal == "hold"
    # odds fine but percentile below 60
    assert _signal(55.0, 0.40).signal == "hold"


def test_rebuild_needs_both_a_low_percentile_and_low_odds():
    assert _signal(30.0, 0.05).signal == "rebuild"
    # percentile in rebuild range but odds above the 0.10 low floor
    assert _signal(30.0, 0.20).signal == "hold"
    # odds low but percentile above 35
    assert _signal(45.0, 0.05).signal == "hold"


def test_thresholds_are_inclusive_at_the_boundary():
    assert _signal(60.0, 0.25).signal == "contend"
    assert _signal(35.0, 0.10).signal == "rebuild"


def test_the_neutral_band_holds():
    assert _signal(50.0, 0.5).signal == "hold"


def test_every_signal_reports_its_inputs_and_recommends_nothing():
    for pct, odds in [(70.0, 0.5), (20.0, 0.02), (50.0, 0.3)]:
        result = _signal(pct, odds)
        assert result.contend_percentile_threshold == 60.0
        assert result.rebuild_percentile_threshold == 35.0
        assert result.striking_distance_playoff_odds == 0.25
        assert result.low_playoff_odds == 0.10
        assert result.recommends_transaction is False
        assert result.rationale  # non-empty explanation
        assert any("no transaction" in r.lower() for r in result.rationale)


def test_the_no_transaction_invariant_cannot_be_constructed_away():
    with pytest.raises(ValueError):
        ContendRebuildHold(
            signal="contend",
            week=8,
            signal_start_week=5,
            points_for_percentile=70.0,
            playoff_odds=0.5,
            contend_percentile_threshold=60.0,
            rebuild_percentile_threshold=35.0,
            striking_distance_playoff_odds=0.25,
            low_playoff_odds=0.10,
            rationale=("x",),
            recommends_transaction=True,
        )
