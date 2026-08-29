"""The v1 opportunity baseline: decay-weighted trailing mean of scored actuals
(issue #16; ADR-0013 §3)."""

from __future__ import annotations

from deadparrots.weekly.identity import PlayerResolver
from deadparrots.weekly.opportunity import (
    player_games,
    target_week_opportunity,
    usage_by_player_week,
)
from deadparrots.weekly.scored_history import ScoredGame


def test_first_game_has_zero_residual_then_trailing_form():
    scored = [ScoredGame(1, 10.0), ScoredGame(2, 20.0), ScoredGame(3, 12.0)]
    games = player_games(scored, season=2026, half_life=4.0)

    assert games[0].expected_points == games[0].actual_points  # no prior → 0 residual
    assert games[1].expected_points == 10.0  # only week 1 in the trailing window
    # week 3 baseline is a decay-weighted blend of weeks 1 and 2, newest heavier
    assert 10.0 < games[2].expected_points < 20.0


def test_target_week_opportunity_is_none_without_history():
    assert target_week_opportunity([], half_life=4.0) is None
    opp = target_week_opportunity([ScoredGame(1, 8.0), ScoredGame(2, 12.0)], half_life=4.0)
    assert opp is not None and 8.0 < opp.expected_points < 12.0


def test_usage_snapshot_from_snaps_and_team_targets():
    resolver = PlayerResolver(
        [{"full_name": "Wr One", "team": "BUF", "position": "WR", "gsis_id": "p1"}]
    )
    player_stats = [
        {
            "player_id": "p1",
            "player_display_name": "Wr One",
            "position": "WR",
            "team": "BUF",
            "week": 1,
            "targets": 6,
        },
        {
            "player_id": "p2",
            "player_display_name": "Wr Two",
            "position": "WR",
            "team": "BUF",
            "week": 1,
            "targets": 4,
        },
    ]
    snaps = [
        {"player": "Wr One", "team": "BUF", "week": 1, "offense_pct": 0.9},
    ]
    usage = usage_by_player_week(player_stats, snaps, resolver)
    snap = usage[("p1", 1)]
    assert snap.snap_share == 0.9
    assert snap.target_share == 0.6  # 6 of the team's 10 targets
