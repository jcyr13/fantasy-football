from __future__ import annotations

from deadparrots.scoring import RIP_TIDE_RULESET, ScoringUnit, score_row
from deadparrots.scoring.adapters import (
    kicker_stat_row,
    offense_stat_row,
    stat_rows_from_player_stats,
    team_defense_stat_row,
)

RULES = RIP_TIDE_RULESET


def test_offense_adapter_maps_nflverse_columns_and_scores():
    record = {
        "player_id": "00-0034796",
        "player_display_name": "Josh Allen",
        "season": 2025,
        "week": 4,
        "passing_yards": 250,
        "passing_tds": 3,
        "passing_interceptions": 1,
        "sacks_suffered": 2,
        "rushing_2pt_conversions": 1,
        "rushing_yards": 10,
        "rushing_tds": 0,
        "receiving_yards": 0,
        "rushing_fumbles_lost": 1,
    }
    row = offense_stat_row(record)
    assert row.unit is ScoringUnit.OFFENSE
    assert row.entity_id == "00-0034796"
    assert row.label == "Josh Allen"
    assert row.key == ("00-0034796", 2025, 4)
    # 10 + 18 - 1 - 2 + 2 + 1
    assert score_row(row, RULES).points == 28.0


def test_offense_adapter_sums_all_three_two_point_conversion_columns():
    row = offense_stat_row(
        {
            "player_id": "x",
            "season": 2025,
            "week": 1,
            "passing_2pt_conversions": 1,
            "rushing_2pt_conversions": 1,
            "receiving_2pt_conversions": 1,
        }
    )
    assert row.stat("two_point_conversions") == 3.0


def test_offense_adapter_falls_back_to_gsis_id_and_tolerates_missing_columns():
    row = offense_stat_row({"gsis_id": "00-1", "season": 2025, "week": 2, "rushing_yards": 30})
    assert row.entity_id == "00-1"
    assert score_row(row, RULES).points == 3.0


def test_kicker_adapter_folds_50_59_and_60_plus_into_one_band():
    record = {
        "player_id": "K1",
        "season": 2025,
        "week": 5,
        "fg_made_30_39": 2,
        "fg_made_50_59": 1,
        "fg_made_60_": 1,
        "pat_made": 4,
    }
    row = kicker_stat_row(record)
    assert row.stat("fg_made_50_plus") == 2.0
    # 6 + 10 + 4
    assert score_row(row, RULES).points == 20.0


def test_stat_rows_from_player_stats_routes_by_position_and_skips_non_scorers():
    records = [
        {"player_id": "qb1", "position": "QB", "season": 2025, "week": 1, "passing_yards": 250},
        {"player_id": "k1", "position": "K", "season": 2025, "week": 1, "pat_made": 3},
        {"player_id": "wr1", "position": "WR", "season": 2025, "week": 1, "receiving_yards": 40},
        {"player_id": "lb1", "position": "LB", "season": 2025, "week": 1, "def_tackles_solo": 9},
        {"player_id": "p1", "position": None, "season": 2025, "week": 1},
    ]
    rows = stat_rows_from_player_stats(records)
    assert [(r.entity_id, r.unit) for r in rows] == [
        ("qb1", ScoringUnit.OFFENSE),
        ("k1", ScoringUnit.KICKER),
        ("wr1", ScoringUnit.OFFENSE),
    ]


def test_stat_rows_from_player_stats_reads_the_recorded_nflverse_fixture(raw_nflverse):
    rows = stat_rows_from_player_stats(raw_nflverse("player_stats").iter_rows(named=True))
    # The fixture holds 2 QB + 2 K rows and nothing else scorable here.
    assert sorted(r.unit for r in rows) == sorted(
        [ScoringUnit.OFFENSE, ScoringUnit.OFFENSE, ScoringUnit.KICKER, ScoringUnit.KICKER]
    )
    scored = {r.entity_id: score_row(r, RULES).points for r in rows}
    # QB 00-0023459 in the fixture: 244 pass yds, 4 pass TD, 0 INT, -1 rush yds.
    assert scored["00-0023459"] == 33.66


def test_team_defense_helper_builds_a_scorable_row():
    row = team_defense_stat_row(
        team="BUF",
        season=2025,
        week=6,
        sacks=3,
        interceptions=1,
        defensive_touchdowns=1,
        points_allowed=13,
    )
    assert row.unit is ScoringUnit.TEAM_DEFENSE
    assert row.entity_id == "BUF"
    # 6 + 2 + 6 + 4(tier)
    assert score_row(row, RULES).points == 18.0
