from __future__ import annotations

from pathlib import Path

import pytest

from deadparrots.scoring import RIP_TIDE_RULESET, ScoringUnit, score_player_weeks
from deadparrots.scoring.oracle import (
    ORACLE_FIXTURE_PATH,
    STAT_ROWS_FIXTURE_PATH,
    load_oracle_fixture,
    load_stat_rows_fixture,
)

# THE VALIDATION GATE (spec issue #1, "Validation gate (hard)").
#
# The scoring engine is not trusted, and nothing in the app is built on it,
# until its output reproduces real 2025 Yahoo per-player weekly fantasy points
# *exactly* (0.00) for every offense / kicker / team-DEF player-week in the RIP
# TIDE League. This is the highest-weight test in the repo.
#
# The golden fixtures are captured once from Yahoo via ``yfpy`` and are not
# checked in until that capture runs — see docs/scoring-oracle-capture.md and
# ``python -m deadparrots.scoring.oracle``. Until both fixture files exist this
# test SKIPS (loudly), so CI stays green while making the outstanding gate
# visible in every run's summary.

pytestmark = pytest.mark.gate

_FIXTURES_PRESENT = ORACLE_FIXTURE_PATH.exists() and STAT_ROWS_FIXTURE_PATH.exists()
_SKIP_REASON = (
    "2025 Yahoo golden fixtures not captured yet: "
    f"expected {ORACLE_FIXTURE_PATH.name} and {STAT_ROWS_FIXTURE_PATH.name} in "
    f"{Path(ORACLE_FIXTURE_PATH).parent}. Run `python -m deadparrots.scoring.oracle` "
    "(see docs/scoring-oracle-capture.md)."
)

# Offense, kicker, and team defense must match to the cent. (IDP, when it lands,
# gets a ±1.0 tolerance and its own outlier catalogue — a separate ticket.)
_EXACT_UNITS = {ScoringUnit.OFFENSE, ScoringUnit.KICKER, ScoringUnit.TEAM_DEFENSE}


@pytest.mark.skipif(not _FIXTURES_PRESENT, reason=_SKIP_REASON)
def test_engine_reproduces_2025_yahoo_actuals_exactly():
    stat_rows = load_stat_rows_fixture()
    oracle = load_oracle_fixture()
    assert oracle, "oracle fixture is empty"

    scored = score_player_weeks(stat_rows, RIP_TIDE_RULESET)

    missing: list[str] = []
    mismatches: list[str] = []
    checked = 0
    for record in oracle:
        if record.unit not in _EXACT_UNITS:
            continue
        result = scored.get(record.key)
        who = record.label or record.entity_id
        if result is None:
            missing.append(f"{record.unit.value} {who} wk{record.week}")
            continue
        checked += 1
        if result.points != record.yahoo_points:
            delta = result.points - record.yahoo_points
            mismatches.append(
                f"{record.unit.value} {who} wk{record.week}: "
                f"engine {result.points:+.2f} vs Yahoo {record.yahoo_points:+.2f} "
                f"(delta {delta:+.2f})"
            )

    report = []
    if missing:
        report.append(f"{len(missing)} oracle player-week(s) had no scored stat row:")
        report += [f"  - {m}" for m in missing[:50]]
    if mismatches:
        report.append(f"{len(mismatches)} of {checked} scored player-week(s) did not match Yahoo:")
        report += [f"  - {m}" for m in mismatches[:50]]
    assert not report, "2025 validation gate FAILED\n" + "\n".join(report)
    assert checked > 0, "gate ran but checked zero offense/kicker/DEF player-weeks"
