from __future__ import annotations

from deadparrots.scoring import ScoringUnit, StatRow
from deadparrots.scoring.oracle import (
    OracleRecord,
    load_oracle_fixture,
    load_stat_rows_fixture,
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
