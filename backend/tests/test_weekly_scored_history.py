"""nflverse player_stats → validated engine → scored weekly history
(issue #16; ADR-0013 §3)."""

from __future__ import annotations

from deadparrots.scoring import ScoringUnit
from deadparrots.weekly.scored_history import (
    scored_games_by_player,
    stat_rows_from_player_stats,
)


def _qb_row(week: int, tds: int) -> dict:
    return {
        "player_id": "00-0000001",
        "player_display_name": "Test QB",
        "position": "QB",
        "season": 2026,
        "week": week,
        "passing_yards": 250,
        "passing_tds": tds,
        "passing_interceptions": 1,
    }


def _ol_row() -> dict:
    return {
        "player_id": "00-0000009",
        "player_display_name": "Left Tackle",
        "position": "T",
        "season": 2026,
        "week": 1,
    }


def test_maps_offense_columns_and_scores_with_the_engine():
    rows = stat_rows_from_player_stats([_qb_row(1, 2), _qb_row(2, 3)])
    assert {r.unit for r in rows} == {ScoringUnit.OFFENSE}
    assert rows[0].stats["passing_touchdowns"] == 2
    assert rows[0].stats["interceptions_thrown"] == 1

    scored = scored_games_by_player(rows)
    games = scored["00-0000001"]
    assert [g.week for g in games] == [1, 2]
    # 250 pass yds @ 25/pt = 10, +2 TD*6 = 12, -1 INT  => 21.0 in week 1
    assert games[0].points == 21.0
    assert games[1].points == 27.0  # the 3-TD week


def test_positions_the_league_never_scores_are_skipped():
    rows = stat_rows_from_player_stats([_ol_row()])
    assert rows == []


def test_idp_row_scored_on_its_own_unit():
    rows = stat_rows_from_player_stats(
        [
            {
                "player_id": "00-0000002",
                "player_display_name": "Test LB",
                "position": "LB",
                "season": 2026,
                "week": 1,
                "def_tackles_solo": 6,
                "def_tackle_assists": 2,
                "def_sacks": 1.0,
                "def_pass_defended": 1,
            }
        ]
    )
    assert rows[0].unit is ScoringUnit.INDIVIDUAL_DEFENSE
    scored = scored_games_by_player(rows)
    # 6 solo*1 + 2 assist*0.5 + 1 sack*2 + 1 PD*1 = 10.0
    assert scored["00-0000002"][0].points == 10.0


def test_kicker_distance_buckets_map():
    rows = stat_rows_from_player_stats(
        [
            {
                "player_id": "00-0000003",
                "player_display_name": "Test K",
                "position": "K",
                "season": 2026,
                "week": 1,
                "fg_made_30_39": 1,
                "fg_made_50_59": 1,
                "pat_made": 2,
            }
        ]
    )
    assert rows[0].unit is ScoringUnit.KICKER
    assert rows[0].stats["fg_made_50_plus"] == 1
    assert rows[0].stats["pat_made"] == 2
