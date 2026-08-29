from __future__ import annotations

import pytest

from deadparrots.scoring import (
    RIP_TIDE_RULESET,
    ScoringUnit,
    StatRow,
    UnknownStatError,
    round_points,
    score_player_weeks,
    score_row,
    total_points,
)

RULES = RIP_TIDE_RULESET


def offense(**stats) -> StatRow:
    return StatRow("p1", 2025, 3, ScoringUnit.OFFENSE, stats, label="Test Player")


def kicker(**stats) -> StatRow:
    return StatRow("k1", 2025, 3, ScoringUnit.KICKER, stats, label="Test Kicker")


def defense(**stats) -> StatRow:
    return StatRow("BUF", 2025, 3, ScoringUnit.TEAM_DEFENSE, stats, label="BUF")


# --------------------------------------------------------------------------- #
# round_points
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (13.4, 13.4),
        (1.005, 1.01),  # half-up, not banker's rounding
        (1.004, 1.0),
        (2.675, 2.68),
        (-1.005, -1.01),  # away from zero on a tie
        (0.0, 0.0),
    ],
)
def test_round_points_is_half_up_two_decimals(raw, expected):
    assert round_points(raw) == expected


# --------------------------------------------------------------------------- #
# Offense
# --------------------------------------------------------------------------- #


def test_offense_full_line_totals_exactly():
    row = offense(
        passing_yards=300,
        passing_touchdowns=2,
        interceptions_thrown=1,
        sacks_taken=2,
        rushing_yards=50,
        rushing_touchdowns=1,
    )
    scored = score_row(row, RULES)
    # 12 + 12 - 1 - 2 + 5 + 6
    assert scored.points == 32.0
    assert scored.unit is ScoringUnit.OFFENSE


def test_offense_yardage_is_fractional():
    row = offense(receiving_yards=74, receiving_touchdowns=1)
    assert score_row(row, RULES).points == 13.4


def test_offense_can_go_negative():
    row = offense(interceptions_thrown=2, sacks_taken=3)
    assert score_row(row, RULES).points == -5.0


def test_offense_two_point_conversions_score_two_each():
    assert score_row(offense(two_point_conversions=2), RULES).points == 4.0


def test_offense_return_yards_score_one_per_twenty_five():
    # A WR with 33 receiving yards and a 129-yard return: 3.3 + 5.16
    row = offense(receiving_yards=33, return_yards=129)
    assert score_row(row, RULES).points == 8.46


def test_offense_player_who_makes_a_tackle_is_credited_individual_defense():
    # 45 receiving yards + 1 solo tackle: RIP TIDE scores the tackle for anyone.
    assert score_row(offense(receiving_yards=45, tackle_solo=1), RULES).points == 5.5
    assert score_row(offense(tackle_assist=3, passes_defended=1), RULES).points == 2.5


def test_offense_fumbles_lost_are_zero_under_current_ruleset():
    assert score_row(offense(rushing_yards=100, fumbles_lost=3), RULES).points == 10.0


def test_offense_breakdown_sums_to_the_unrounded_total():
    row = offense(passing_yards=263, passing_touchdowns=1, interceptions_thrown=1)
    scored = score_row(row, RULES)
    assert scored.breakdown["passing_yards"] == 263 / 25
    assert scored.breakdown["passing_touchdowns"] == 6.0
    assert scored.breakdown["interceptions_thrown"] == -1.0
    assert round_points(sum(scored.breakdown.values())) == scored.points


# --------------------------------------------------------------------------- #
# Kicker
# --------------------------------------------------------------------------- #


def test_kicker_distance_tiers_and_pats():
    row = kicker(
        fg_made_20_29=2,
        fg_made_40_49=1,
        fg_made_50_plus=1,
        pat_made=3,
        fg_missed_0_19=1,
    )
    # 6 + 4 + 5 + 3 - 1
    assert score_row(row, RULES).points == 17.0


def test_kicker_long_misses_do_not_score():
    # Only 0-19 misses are penalised; there is no stat key for longer misses.
    assert score_row(kicker(fg_made_30_39=1), RULES).points == 3.0


def test_kicker_missed_pat_is_minus_one():
    assert score_row(kicker(pat_made=2, pat_missed=1), RULES).points == 1.0


def test_kicker_who_makes_a_tackle_on_the_return_is_credited():
    # 4 PATs + 1 assisted tackle = 4 + 0.5
    assert score_row(kicker(pat_made=4, tackle_assist=1), RULES).points == 4.5


# --------------------------------------------------------------------------- #
# Team defense
# --------------------------------------------------------------------------- #


def test_team_defense_events_plus_points_allowed_bonus():
    row = defense(
        sacks=4,
        interceptions=2,
        fumble_recoveries=1,
        defensive_touchdowns=1,
        blocked_kicks=1,
        tackles_for_loss=3,
        points_allowed=17,
    )
    # 8 + 4 + 1 + 6 + 2 + 3 + 1(tier)
    assert score_row(row, RULES).points == 25.0


def test_team_defense_shutout_bonus():
    assert score_row(defense(points_allowed=0), RULES).points == 10.0


def test_team_defense_return_yards_score_one_per_twenty_five():
    # 2 sacks + 86 return yards + points_allowed 3 (tier +7): 4 + 3.44 + 7
    row = defense(sacks=2, return_yards=86, points_allowed=3)
    assert score_row(row, RULES).points == 14.44


def test_team_defense_blowout_allowed_is_minus_four():
    assert score_row(defense(sacks=1, points_allowed=41), RULES).points == -2.0


def test_team_defense_points_allowed_defaults_to_shutout_tier_when_absent():
    # A row with no points_allowed stat is treated as 0 allowed -> +10.
    assert score_row(defense(sacks=0), RULES).points == 10.0


# --------------------------------------------------------------------------- #
# Dispatch / aggregation / validation
# --------------------------------------------------------------------------- #


def test_score_player_weeks_keys_by_entity_season_week():
    rows = [
        offense(passing_yards=250),
        kicker(pat_made=1),
        defense(points_allowed=3),
    ]
    scored = score_player_weeks(rows, RULES)
    assert set(scored) == {("p1", 2025, 3), ("k1", 2025, 3), ("BUF", 2025, 3)}
    assert scored[("p1", 2025, 3)].points == 10.0
    assert scored[("BUF", 2025, 3)].points == 7.0


def test_total_points_sums_a_lineup():
    rows = [
        StatRow("p1", 2025, 3, ScoringUnit.OFFENSE, {"rushing_yards": 100}),
        StatRow(
            "p2", 2025, 3, ScoringUnit.OFFENSE,
            {"receiving_yards": 50, "receiving_touchdowns": 1},
        ),
    ]
    scored = score_player_weeks(rows, RULES)
    assert total_points(scored) == 21.0


def test_unknown_stat_key_is_rejected_at_row_construction():
    with pytest.raises(UnknownStatError) as excinfo:
        StatRow("p1", 2025, 3, ScoringUnit.OFFENSE, {"punt_yards": 40})
    assert "punt_yards" in str(excinfo.value)


def test_missing_stats_default_to_zero():
    assert score_row(offense(), RULES).points == 0.0
    assert score_row(kicker(), RULES).points == 0.0


def test_scored_player_week_is_immutable_and_carries_identity():
    scored = score_row(offense(passing_yards=100), RULES)
    assert scored.key == ("p1", 2025, 3)
    with pytest.raises(Exception):
        scored.points = 99.0  # type: ignore[misc]
