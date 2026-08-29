from __future__ import annotations

import pytest

from deadparrots.scoring import RIP_TIDE_RULESET, ScoringUnit, score_player_weeks
from deadparrots.scoring.oracle import (
    IDP_TOLERANCE,
    load_idp_outlier_catalogue,
    load_oracle_fixture,
    load_stat_rows_fixture,
)

# THE IDP VALIDATION GATE (spec issue #1, "IDP / D slot"; ticket #5).
#
# The individual-defender ("D") slot is scored as its own surface, distinct from
# team DEF. It is validated against the same 2025 Yahoo box-score oracle as the
# offense/kicker/DEF gate, but held to a ±1.0 tolerance instead of the cent:
# Yahoo's live scorer splits solo vs. assisted tackles, half-sacks, and TFLs
# differently from the final NFL gamebook often enough that an exact match is not
# achievable from gamebook stats. Every player-week outside ±1.0 must appear in
# the committed outlier catalogue ``yahoo_2025_idp_outliers.json`` with a stated
# cause — it is never silently accepted.
#
# Runs as its own CI step (`pytest -m gate`), alongside the exact gate.

pytestmark = pytest.mark.gate


def _idp_scored_vs_oracle():
    stat_rows = load_stat_rows_fixture()
    oracle = [r for r in load_oracle_fixture() if r.unit is ScoringUnit.INDIVIDUAL_DEFENSE]
    assert oracle, "no individual-defender records in the oracle fixture"
    scored = score_player_weeks(stat_rows, RIP_TIDE_RULESET)
    return oracle, scored


def test_every_idp_player_week_is_within_tolerance_or_catalogued():
    oracle, scored = _idp_scored_vs_oracle()
    catalogue = {o.key for o in load_idp_outlier_catalogue()}

    missing: list[str] = []
    uncatalogued: list[str] = []
    checked = 0
    for record in oracle:
        result = scored.get(record.key)
        who = record.label or record.entity_id
        if result is None:
            missing.append(f"{who} wk{record.week}")
            continue
        checked += 1
        delta = result.points - record.yahoo_points
        if abs(delta) > IDP_TOLERANCE and record.key not in catalogue:
            uncatalogued.append(
                f"{who} wk{record.week}: engine {result.points:+.2f} vs "
                f"Yahoo {record.yahoo_points:+.2f} (delta {delta:+.2f})"
            )

    report: list[str] = []
    if missing:
        report.append(f"{len(missing)} IDP oracle player-week(s) had no scored stat row:")
        report += [f"  - {m}" for m in missing]
    if uncatalogued:
        report.append(
            f"{len(uncatalogued)} IDP player-week(s) outside ±{IDP_TOLERANCE:.1f} "
            "and not in yahoo_2025_idp_outliers.json (add them with a stated cause):"
        )
        report += [f"  - {m}" for m in uncatalogued]
    assert not report, "IDP validation gate FAILED\n" + "\n".join(report)
    assert checked >= 40, f"IDP gate only checked {checked} player-weeks — fixture looks truncated"


def test_outlier_catalogue_has_no_stale_or_unexplained_entries():
    """Every catalogued entry must name a real, still-out-of-tolerance IDP
    player-week, record the true discrepancy, and carry a non-empty cause — the
    catalogue cannot rot into a silent allowlist.
    """
    oracle, scored = _idp_scored_vs_oracle()
    by_key = {r.key: r for r in oracle}

    problems: list[str] = []
    for outlier in load_idp_outlier_catalogue():
        tag = f"{outlier.entity_id} wk{outlier.week}"
        if not outlier.cause.strip():
            problems.append(f"{tag}: empty cause")
        record = by_key.get(outlier.key)
        result = scored.get(outlier.key)
        if record is None or result is None:
            problems.append(f"{tag}: not an IDP oracle player-week")
            continue
        if abs(result.points - record.yahoo_points) <= IDP_TOLERANCE:
            problems.append(f"{tag}: now within tolerance — remove it")
        if outlier.yahoo_points != record.yahoo_points:
            problems.append(
                f"{tag}: catalogued yahoo_points {outlier.yahoo_points} "
                f"!= oracle {record.yahoo_points}"
            )
        if outlier.engine_points != result.points:
            problems.append(
                f"{tag}: catalogued engine_points {outlier.engine_points} "
                f"!= current engine {result.points}"
            )
    assert not problems, "outlier catalogue is stale\n" + "\n".join(f"  - {p}" for p in problems)


def test_idp_is_scored_as_a_distinct_surface_not_team_defense():
    oracle, scored = _idp_scored_vs_oracle()
    for record in oracle:
        result = scored[record.key]
        assert result.unit is ScoringUnit.INDIVIDUAL_DEFENSE
        # No points-allowed component — that is a team-DEF-only concept.
        assert "points_allowed" not in result.breakdown
