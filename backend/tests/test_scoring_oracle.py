from __future__ import annotations

import pytest

from deadparrots.scoring import RIP_TIDE_RULESET, ScoringUnit, StatRow, score_row
from deadparrots.scoring.oracle import (
    OracleRecord,
    UnmappedStatLabelError,
    load_oracle_fixture,
    load_stat_rows_fixture,
    records_from_box_scores,
    stat_rows_from_json,
    stat_rows_to_json,
    write_oracle_fixture,
    write_stat_rows_fixture,
)


def test_oracle_fixture_round_trips(tmp_path):
    records = [
        OracleRecord("00-0034796", 2025, 1, ScoringUnit.OFFENSE, 24.56, "Josh Allen"),
        OracleRecord("BUF", 2025, 1, ScoringUnit.TEAM_DEFENSE, 9.0, "BUF"),
        OracleRecord("K1", 2025, 2, ScoringUnit.KICKER, 11.0, None),
    ]
    path = write_oracle_fixture(records, tmp_path / "oracle.json")

    loaded = load_oracle_fixture(path)
    assert {r.key: r for r in loaded} == {r.key: r for r in records}
    assert {r.unit for r in loaded} == {
        ScoringUnit.OFFENSE,
        ScoringUnit.TEAM_DEFENSE,
        ScoringUnit.KICKER,
    }


def test_stat_rows_fixture_round_trips(tmp_path):
    rows = [
        StatRow(
            "00-1", 2025, 1, ScoringUnit.OFFENSE,
            {"passing_yards": 300, "passing_touchdowns": 2},
        ),
        StatRow("BUF", 2025, 1, ScoringUnit.TEAM_DEFENSE, {"sacks": 3, "points_allowed": 17}),
    ]
    path = write_stat_rows_fixture(rows, tmp_path / "rows.json")

    loaded = load_stat_rows_fixture(path)
    assert {r.key: dict(r.stats) for r in loaded} == {r.key: dict(r.stats) for r in rows}
    assert loaded[0].unit is ScoringUnit.OFFENSE


def test_stat_rows_from_json_drops_keys_outside_the_unit_vocabulary():
    data = stat_rows_to_json(
        [StatRow("p", 2025, 1, ScoringUnit.OFFENSE, {"passing_yards": 100})]
    )
    data[0]["stats"]["legacy_metric"] = 5.0  # a key a future nflverse dump might add

    (row,) = stat_rows_from_json(data)
    assert "legacy_metric" not in row.stats
    assert row.stat("passing_yards") == 100.0


# --------------------------------------------------------------------------- #
# Box-score transform
# --------------------------------------------------------------------------- #


def test_transform_classifies_and_maps_an_offensive_line():
    raw = {"Deebo Samuel Sr.|1": [17.6, [
        ["Rushing Yards", "19"], ["Rushing Touchdowns", "1"],
        ["Receiving Yards", "77"], ["Return Yards", "50"],
    ]]}
    oracle, rows = records_from_box_scores(raw)
    (rec,), (row,) = oracle, rows
    assert rec.unit is ScoringUnit.OFFENSE
    assert rec.entity_id == "Deebo Samuel Sr." and rec.week == 1
    assert rec.yahoo_points == 17.6
    assert row.stat("return_yards") == 50.0
    # engine re-derives the same total from the mapped counts
    assert score_row(row, RIP_TIDE_RULESET).points == 17.6


def test_transform_reads_team_defense_by_nickname_and_fills_absent_points_allowed():
    # "Rams" allowed 21-27 -> Yahoo omits the line -> transform supplies the 0-tier value.
    raw = {"Rams|5": [10.72, [["Sack", "1"], ["Return Yards", "143"], ["Tackles for Loss", "3"]]]}
    (rec,), (row,) = records_from_box_scores(raw)
    assert rec.unit is ScoringUnit.TEAM_DEFENSE
    assert row.stat("points_allowed") == 24.0
    assert score_row(row, RIP_TIDE_RULESET).points == 10.72


def test_transform_classifies_a_pure_individual_defender_as_the_d_slot():
    raw = {
        "Roquan Smith|1": [9.0, [["Tackle Solo", "8"], ["Tackle Assist", "2"]]],
        "Jordyn Brooks|1": [10.5, [
            ["Tackle Solo", "5"], ["Tackle Assist", "9"], ["Tackles for Loss", "1"],
        ]],
    }
    oracle, rows = records_from_box_scores(raw)
    assert {r.unit for r in oracle} == {ScoringUnit.INDIVIDUAL_DEFENSE}
    by_name = {r.entity_id: r for r in rows}
    assert by_name["Roquan Smith"].stat("tackle_solo") == 8.0
    # engine re-derives each Yahoo total from the mapped counts (within tolerance)
    for row, rec in zip(rows, oracle, strict=True):
        assert abs(score_row(row, RIP_TIDE_RULESET).points - rec.yahoo_points) <= 1.0


def test_transform_maps_idp_turnover_return_yards_and_forced_fumble():
    # 3 solo (3) + 1 INT (2) + 1 forced fumble (1) + 40 turnover-return yds (1.6)
    raw = {"Kerby Joseph|9": [7.6, [
        ["Tackle Solo", "3"], ["Interception", "1"], ["Fumble Force", "1"],
        ["Turnover Return Yards", "40"],
    ]]}
    (rec,), (row,) = records_from_box_scores(raw)
    assert rec.unit is ScoringUnit.INDIVIDUAL_DEFENSE
    assert row.stat("forced_fumbles") == 1.0
    assert row.stat("turnover_return_yards") == 40.0
    assert score_row(row, RIP_TIDE_RULESET).points == 7.6


def test_transform_raises_on_an_unmapped_yahoo_label():
    raw = {"Someone|1": [1.0, [["Passing Yards", "25"], ["Fabricated Stat", "1"]]]}
    with pytest.raises(UnmappedStatLabelError):
        records_from_box_scores(raw)
