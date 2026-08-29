from __future__ import annotations

import pytest

from deadparrots.lineup import Lineup, swing_players
from lineup_helpers import rp, ten_starters

SEED = 735806
TRIALS = 4_000


def _dead_parrots() -> Lineup:
    return Lineup(tuple(sorted(ten_starters(mean=12.0), key=lambda p: p.player_id)))


def test_ranks_are_contiguous_and_ordered_by_variance_contribution():
    opp = ten_starters(mean=12.0, prefix="opp")
    ranked = swing_players(_dead_parrots(), opp, rng_seed=SEED, n_trials=TRIALS)

    assert [s.rank for s in ranked] == list(range(1, len(opp) + 1))
    contributions = [s.variance_contribution for s in ranked]
    assert contributions == sorted(contributions, reverse=True)


def test_the_highest_variance_opponent_starter_swings_the_most():
    opp = [
        rp("o-qb", "QB", mean=18.0, sigma=4.0),
        rp("o-rb1", "RB", mean=12.0, sigma=4.0),
        rp("o-rb2", "RB", mean=11.0, sigma=4.0),
        rp("o-wr1", "WR", mean=14.0, sigma=4.0),
        rp("o-wr2", "WR", mean=12.0, sigma=4.0),
        rp("o-boom", "WR", mean=12.0, sigma=18.0),  # the boom/bust swing player
        rp("o-te", "TE", mean=8.0, sigma=3.0),
        rp("o-k", "K", mean=8.0, sigma=2.0),
        rp("o-def", "DEF", mean=7.0, sigma=3.0),
        rp("o-d", "IDP", mean=7.0, sigma=0.5),  # near-deterministic
    ]
    ranked = swing_players(_dead_parrots(), opp, rng_seed=SEED, n_trials=TRIALS)

    assert ranked[0].player_id == "o-boom"
    assert ranked[-1].player_id == "o-d"
    assert ranked[0].variance_share > ranked[-1].variance_share


def test_variance_share_is_the_contribution_over_one_margin_variance():
    opp = ten_starters(mean=12.0, prefix="opp")
    ranked = swing_players(_dead_parrots(), opp, rng_seed=SEED, n_trials=TRIALS)

    # every entry's share is its own contribution over the *same* Var(margin)
    ratios = [
        s.variance_contribution / s.variance_share
        for s in ranked
        if s.variance_share != 0.0
    ]
    assert ratios
    assert all(r == pytest.approx(ratios[0]) for r in ratios)
    assert ratios[0] > 0.0
