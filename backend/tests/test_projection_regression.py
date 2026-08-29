from __future__ import annotations

import json
from pathlib import Path

import pytest

from deadparrots.projection import project
from projection_cases import CASES, case_by_name, expected_payload

# Golden regression: every scenario in ``projection_cases.CASES`` has its full
# output frozen in ``fixtures/projection/regression.json``. An intended model
# change is a deliberate ``uv run python scripts/gen_projection_fixtures.py`` +
# a reviewed diff; anything else trips these assertions.

FIXTURE = Path(__file__).parent / "fixtures" / "projection" / "regression.json"

_FIXTURE_CASES = {c["name"]: c["expected"] for c in json.loads(FIXTURE.read_text())}


@pytest.mark.parametrize("name", [c.name for c in CASES])
def test_regression_case_matches_frozen_fixture(name):
    case = case_by_name(name)
    expected = _FIXTURE_CASES[name]

    result = project(
        case.history,
        case.opportunity,
        season=case.season,
        week=case.week,
        consensus_points=case.consensus_points,
        matchup=case.matchup,
        rng_seed=case.rng_seed,
    )

    # exact — these are what the UI shows
    assert result.floor == expected["floor"]
    assert result.projection == expected["projection"]
    assert result.ceiling == expected["ceiling"]
    assert result.low_confidence == expected["low_confidence"]
    assert list(result.reasons) == expected["reasons"]

    ec = expected["components"]
    c = result.components
    assert c.source == ec["source"]
    assert c.current_season_games == ec["current_season_games"]
    for field in (
        "mean_base",
        "opportunity_trend_slope",
        "opportunity_trend_multiplier",
        "matchup_factor",
        "matchup_factor_raw",
        "mean_final",
        "shape_own_weight",
        "residual_cv",
        "residual_skew",
    ):
        assert getattr(c, field) == pytest.approx(ec[field], rel=1e-9, abs=1e-12), field


@pytest.mark.parametrize("name", [c.name for c in CASES])
def test_regression_cases_hold_the_hard_invariants(name):
    case = case_by_name(name)
    result = project(
        case.history,
        case.opportunity,
        season=case.season,
        week=case.week,
        consensus_points=case.consensus_points,
        matchup=case.matchup,
        rng_seed=case.rng_seed,
    )
    # P10 < P50 < P90, always (methodology §3.1)
    assert result.floor < result.projection < result.ceiling
    # matchup factor never outside ±20% (methodology §3.5)
    assert 0.80 <= result.components.matchup_factor <= 1.20


def test_fixture_file_is_in_sync_with_the_case_list():
    """The committed fixture covers exactly the current scenarios — a new case
    without a regenerated fixture (or vice versa) fails here rather than
    KeyError-ing mid-parametrize.
    """
    assert set(_FIXTURE_CASES) == {c.name for c in CASES}


def test_fixture_payloads_are_what_the_model_produces_now():
    """Belt-and-braces: regenerating in-memory reproduces the committed file,
    so ``scripts/gen_projection_fixtures.py`` and the fixture never drift.
    """
    live = {c.name: expected_payload(c) for c in CASES}
    assert live == _FIXTURE_CASES
