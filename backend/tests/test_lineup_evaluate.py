from __future__ import annotations

import pytest

from deadparrots.lineup import enumerate_lineups, evaluate_lineups
from deadparrots.simulation import simulate_head_to_head
from lineup_helpers import a_roster, ten_starters

SEED = 735806
TRIALS = 1_000


def test_every_candidate_gets_all_five_metrics():
    roster = a_roster(qb=2, rb=3, wr=3, te=2)
    candidates = list(enumerate_lineups(roster))
    opponent = [p.sim for p in ten_starters()]

    evaluations = evaluate_lineups(
        candidates, opponent, rng_seed=SEED, n_trials=TRIALS
    )

    assert len(evaluations) == len(candidates)
    for ev in evaluations:
        assert 0.0 <= ev.p_win <= 1.0
        assert ev.p10 <= ev.p50 <= ev.p90
        assert ev.expected_points > 0.0


def test_evaluation_reproduces_a_full_head_to_head_exactly():
    # The CRN decomposition (sample each player once, sum the arrays) must give
    # byte-identical numbers to simulate_head_to_head on the same lineup and
    # seed — that is what lets the optimizer trust candidate-vs-candidate gaps.
    roster = a_roster(qb=2, rb=3, wr=3, te=2)
    candidates = list(enumerate_lineups(roster))
    opponent_players = ten_starters()
    opponent = [p.sim for p in opponent_players]

    evaluations = evaluate_lineups(
        candidates, opponent, rng_seed=SEED, n_trials=TRIALS
    )

    for ev in evaluations[:12]:
        h2h = simulate_head_to_head(
            ev.lineup.sims, opponent, rng_seed=SEED, n_trials=TRIALS
        )
        assert ev.p_win == h2h.p_win
        assert ev.expected_points == h2h.dead_parrots.mean
        assert ev.p10 == h2h.dead_parrots.p10
        assert ev.p50 == h2h.dead_parrots.p50
        assert ev.p90 == h2h.dead_parrots.p90


def test_same_lineup_evaluates_identically_across_batches():
    roster = a_roster(qb=2, rb=3, wr=3, te=2)
    candidates = list(enumerate_lineups(roster))
    opponent = [p.sim for p in ten_starters()]

    first = evaluate_lineups(candidates, opponent, rng_seed=SEED, n_trials=TRIALS)
    shuffled = list(reversed(candidates))
    second = evaluate_lineups(shuffled, opponent, rng_seed=SEED, n_trials=TRIALS)

    by_ids = {frozenset(ev.lineup.player_ids): ev for ev in second}
    for ev in first:
        other = by_ids[frozenset(ev.lineup.player_ids)]
        assert (ev.p_win, ev.expected_points, ev.p10, ev.p50, ev.p90) == (
            other.p_win,
            other.expected_points,
            other.p10,
            other.p50,
            other.p90,
        )


def test_empty_opponent_is_rejected():
    roster = a_roster(qb=1, rb=2, wr=3, te=1)
    with pytest.raises(ValueError):
        evaluate_lineups(list(enumerate_lineups(roster)), [], rng_seed=SEED)
