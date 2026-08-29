from __future__ import annotations

import pytest

from deadparrots.lineup import (
    OpponentLineup,
    enumerate_lineups,
    optimize_lineups,
)
from lineup_helpers import a_roster, rp, ten_starters

SEED = 735806
TRIALS = 800


def _roster():
    return a_roster(qb=2, rb=3, wr=3, te=2, k=1, def_=1, idp=1)


def _opponent(mean: float = 12.0) -> OpponentLineup:
    return OpponentLineup(
        players=tuple(ten_starters(mean=mean, prefix="opp")),
        assumption="yahoo-set",
        notes=("test opponent",),
    )


def test_reports_all_four_named_lineups_each_the_argmax_of_its_metric():
    result = optimize_lineups(
        _roster(), _opponent(), rng_seed=SEED, n_trials=TRIALS
    )
    evals = result.evaluations
    assert result.n_candidates == len(list(enumerate_lineups(_roster())))

    assert result.max_p_win.p_win == max(e.p_win for e in evals)
    assert result.max_ev.expected_points == max(e.expected_points for e in evals)
    assert result.floor.p10 == max(e.p10 for e in evals)
    assert result.ceiling.p90 == max(e.p90 for e in evals)
    assert result.median.p50 == max(e.p50 for e in evals)
    assert result.recommendation is result.max_p_win


def test_head_to_head_matches_the_recommended_lineup():
    result = optimize_lineups(
        _roster(), _opponent(), rng_seed=SEED, n_trials=TRIALS
    )
    assert result.head_to_head.p_win == result.max_p_win.p_win
    assert result.head_to_head.dead_parrots.mean == result.max_p_win.expected_points


def test_gap_drivers_and_swing_players_are_populated_for_the_recommendation():
    result = optimize_lineups(
        _roster(), _opponent(), rng_seed=SEED, n_trials=TRIALS
    )
    assert len(result.gap_drivers) == 10
    assert len(result.swing_players) == 10
    assert [s.rank for s in result.swing_players] == list(range(1, 11))


def test_opponent_assumption_is_carried_through():
    result = optimize_lineups(
        _roster(), _opponent(), rng_seed=SEED, n_trials=TRIALS
    )
    assert result.opponent_assumption == "yahoo-set"
    assert result.opponent_notes == ("test opponent",)


def test_a_bare_opponent_sequence_is_accepted_and_marked_provided():
    result = optimize_lineups(
        _roster(),
        ten_starters(prefix="opp"),
        rng_seed=SEED,
        n_trials=TRIALS,
    )
    assert result.opponent_assumption == "provided"


# --- acceptance criterion 3: the threshold-rule toggle ----------------------


def test_threshold_rule_recommends_the_floor_lineup_when_favored():
    result = optimize_lineups(
        _roster(),
        _opponent(),
        rng_seed=SEED,
        n_trials=TRIALS,
        favored_threshold=0.0,  # force "favored"
    )
    assert result.threshold_rule.branch == "favored-optimize-floor"
    assert result.threshold_rule.evaluation is result.floor


def test_threshold_rule_recommends_the_ceiling_lineup_when_underdog():
    result = optimize_lineups(
        _roster(),
        _opponent(),
        rng_seed=SEED,
        n_trials=TRIALS,
        favored_threshold=1.0,
        underdog_threshold=1.0,  # force "underdog"
    )
    assert result.threshold_rule.branch == "underdog-optimize-ceiling"
    assert result.threshold_rule.evaluation is result.ceiling


def test_threshold_rule_recommends_the_median_lineup_in_the_coin_flip_band():
    result = optimize_lineups(
        _roster(),
        _opponent(),
        rng_seed=SEED,
        n_trials=TRIALS,
        favored_threshold=1.0,
        underdog_threshold=0.0,  # force the middle band
    )
    assert result.threshold_rule.branch == "coin-flip-optimize-median"
    assert result.threshold_rule.evaluation is result.median


def test_threshold_rule_reads_the_situation_from_the_max_p_win_lineup():
    strong = [rp(f"dp{i}", pos, mean=m) for i, (pos, m) in enumerate(
        [("QB", 40), ("RB", 30), ("RB", 30), ("RB", 28),
         ("WR", 30), ("WR", 30), ("WR", 28),
         ("TE", 25), ("TE", 22), ("K", 20), ("DEF", 20), ("IDP", 20)]
    )]
    result = optimize_lineups(strong, _opponent(mean=6.0), rng_seed=SEED, n_trials=TRIALS)
    assert result.threshold_rule.situation_p_win == result.max_p_win.p_win
    assert result.threshold_rule.situation_p_win > 0.65
    assert result.threshold_rule.branch == "favored-optimize-floor"


def test_empty_roster_is_rejected():
    with pytest.raises(ValueError):
        optimize_lineups([], _opponent(), rng_seed=SEED, n_trials=TRIALS)
