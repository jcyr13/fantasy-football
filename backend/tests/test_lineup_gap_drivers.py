from __future__ import annotations

import math

import pytest

from deadparrots.lineup import Lineup, gap_drivers, total_expected_gap
from deadparrots.simulation import simulate_head_to_head
from lineup_helpers import rp, ten_starters

SEED = 735806


def _dead_parrots_lineup() -> Lineup:
    return Lineup(tuple(sorted(ten_starters(mean=13.0), key=lambda p: p.player_id)))


def _opponent() -> list:
    return ten_starters(mean=11.0, prefix="opp")


def test_one_driver_per_slot_in_display_order():
    drivers = gap_drivers(_dead_parrots_lineup(), _opponent())
    assert [d.slot for d in drivers] == [
        "QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "K", "DEF", "D"
    ]


def test_decomposition_sums_to_the_expected_points_difference_exactly():
    dp = _dead_parrots_lineup()
    opp = _opponent()
    drivers = gap_drivers(dp, opp)

    analytic_gap = math.fsum(p.sim.mean for p in dp.players) - math.fsum(
        p.sim.mean for p in opp
    )
    assert total_expected_gap(drivers) == pytest.approx(analytic_gap, abs=1e-9)
    assert math.fsum(d.contribution for d in drivers) == pytest.approx(
        analytic_gap, abs=1e-9
    )


def test_decomposition_total_matches_the_simulated_mean_margin():
    dp = _dead_parrots_lineup()
    opp = _opponent()
    drivers = gap_drivers(dp, opp)

    h2h = simulate_head_to_head(
        dp.sims, [p.sim for p in opp], rng_seed=SEED, n_trials=4_000
    )
    # analytic decomposition vs Monte-Carlo margin: equal up to sampling error
    assert total_expected_gap(drivers) == pytest.approx(h2h.mean_margin, abs=0.5)


def test_a_slot_where_dead_parrots_out_project_shows_a_positive_contribution():
    dp = Lineup(
        tuple(
            sorted(
                [
                    rp("qb", "QB", mean=30.0),  # big edge at QB
                    rp("rb1", "RB", mean=10.0), rp("rb2", "RB", mean=10.0),
                    rp("wr1", "WR", mean=10.0), rp("wr2", "WR", mean=10.0),
                    rp("wr3", "WR", mean=10.0),
                    rp("te", "TE", mean=10.0),
                    rp("k", "K", mean=10.0),
                    rp("def", "DEF", mean=10.0),
                    rp("d", "IDP", mean=10.0),
                ],
                key=lambda p: p.player_id,
            )
        )
    )
    opp = [
        rp("o-qb", "QB", mean=15.0),
        rp("o-rb1", "RB", mean=10.0), rp("o-rb2", "RB", mean=10.0),
        rp("o-wr1", "WR", mean=10.0), rp("o-wr2", "WR", mean=10.0),
        rp("o-wr3", "WR", mean=10.0),
        rp("o-te", "TE", mean=10.0),
        rp("o-k", "K", mean=10.0),
        rp("o-def", "DEF", mean=10.0),
        rp("o-d", "IDP", mean=10.0),
    ]
    drivers = {d.slot: d for d in gap_drivers(dp, opp)}
    assert drivers["QB"].contribution == pytest.approx(15.0)
    assert drivers["K"].contribution == pytest.approx(0.0)
