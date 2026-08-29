from __future__ import annotations

import json

import pytest

from deadparrots.scoring import RIP_TIDE_RULESET, ScoringUnit, score_player_weeks
from deadparrots.scoring.oracle import (
    BOX_SCORE_RAW_PATH,
    load_oracle_fixture,
    load_stat_rows_fixture,
    records_from_box_scores,
    stat_rows_to_json,
)

# THE VALIDATION GATE (spec issue #1, "Validation gate (hard)").
#
# The scoring engine is not trusted, and nothing in the app is built on it,
# until its output reproduces real 2025 Yahoo per-player weekly fantasy points
# *exactly* (0.00) for every offense / kicker / team-DEF player-week in the RIP
# TIDE League. This is the highest-weight test in the repo and runs as its own
# CI step (`pytest -m gate`).
#
# The oracle is the golden fixture ``yahoo_2025_oracle.json`` — Yahoo's own
# per-player weekly totals scraped from the archived 2025 league's box scores,
# for weeks 1 / 5 / 9 / 13, all 12 teams. ``yahoo_2025_stat_rows.json`` holds
# the matching stat lines the engine scores. Both are regenerated from
# ``yahoo_2025_box_scores.raw.json`` by ``python -m deadparrots.scoring.oracle
# build`` (see docs/scoring-oracle-capture.md).
#
# Individual defenders (the "D" slot) are in the same fixtures but held to a
# ±1.0 tolerance with an explicit outlier catalogue — that is a separate gate,
# ``test_scoring_idp_gate.py`` (ticket #5). This test skips them.

pytestmark = pytest.mark.gate

# Offense, kicker, and team defense must match to the cent.
_EXACT_UNITS = {ScoringUnit.OFFENSE, ScoringUnit.KICKER, ScoringUnit.TEAM_DEFENSE}


def test_engine_reproduces_2025_yahoo_actuals_exactly():
    stat_rows = load_stat_rows_fixture()
    oracle = [r for r in load_oracle_fixture() if r.unit in _EXACT_UNITS]
    assert oracle, "oracle fixture is empty"

    scored = score_player_weeks(stat_rows, RIP_TIDE_RULESET)

    missing: list[str] = []
    mismatches: list[str] = []
    checked = 0
    for record in oracle:
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
    assert checked > 300, f"gate only checked {checked} player-weeks — fixture looks truncated"


def test_committed_fixtures_match_a_fresh_transform_of_the_raw_scrape():
    """The two fixtures are generated from ``yahoo_2025_box_scores.raw.json``;
    they must never drift from what ``oracle build`` would write today.
    """
    raw = json.loads(BOX_SCORE_RAW_PATH.read_text())
    oracle, stat_rows = records_from_box_scores(raw)

    fresh_oracle = {(r.entity_id, r.week): r.yahoo_points for r in oracle}
    committed_oracle = {(r.entity_id, r.week): r.yahoo_points for r in load_oracle_fixture()}
    assert fresh_oracle == committed_oracle

    def _sorted(rows):
        return sorted(
            stat_rows_to_json(rows), key=lambda d: (d["unit"], d["entity_id"], d["week"])
        )

    assert _sorted(stat_rows) == _sorted(load_stat_rows_fixture())
