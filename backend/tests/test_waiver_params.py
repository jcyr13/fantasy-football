from __future__ import annotations

from datetime import date

import pytest

from deadparrots.waiver import (
    DEFAULT_WAIVER_PARAMS,
    WaiverParams,
    last_tuesday_of_august,
)

# The §5 methodology table stops at the Trade Desk; the waiver knobs are
# build-time magnitudes (ADR-0011). These tests pin the shipped defaults and the
# coherence rules so a drift is a deliberate, reviewed change.


def test_shipped_defaults():
    p = DEFAULT_WAIVER_PARAMS
    assert p.big_upgrade_points == 20.0
    assert p.marginal_upgrade_points == 8.0
    assert p.protect_priority_rank == 6
    assert p.bye_crunch_warn_count == 2  # mirrors methodology §5 row 10
    assert p.roster_cutdown_date is None
    assert p.cutdown_window_days == 2
    assert p.cutdown_window_lookahead_days == 7


def test_cutdown_date_defaults_to_last_tuesday_of_august():
    assert last_tuesday_of_august(2026) == date(2026, 8, 25)
    assert last_tuesday_of_august(2025) == date(2025, 8, 26)
    assert last_tuesday_of_august(2024) == date(2024, 8, 27)
    assert DEFAULT_WAIVER_PARAMS.cutdown_date_for(2026) == date(2026, 8, 25)


def test_explicit_cutdown_date_overrides_the_default():
    p = WaiverParams(roster_cutdown_date=date(2026, 8, 26))
    assert p.cutdown_date_for(2026) == date(2026, 8, 26)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"marginal_upgrade_points": -1.0},
        {"big_upgrade_points": 5.0, "marginal_upgrade_points": 8.0},
        {"protect_priority_rank": 0},
        {"bye_crunch_warn_count": 0},
        {"cutdown_window_days": 0},
        {"cutdown_window_lookahead_days": -1},
    ],
)
def test_incoherent_params_raise(kwargs):
    with pytest.raises(ValueError):
        WaiverParams(**kwargs)
