from __future__ import annotations

import dataclasses
import statistics

import pytest

from deadparrots.projection import OpportunityMetrics, PlayerGame, PlayerHistory, project
from deadparrots.simulation import (
    DEFAULT_TRIALS,
    SimPlayer,
    sample_lineup_totals,
    sim_player_from_projection,
    simulate_head_to_head,
)

# Issue #10. Every call fixes ``rng_seed`` so the Monte Carlo is reproducible.
# Acceptance criteria, in order:
#   1. a 10,000-trial head-to-head sim returns P(win) and summary stats
#   2. seed is derived from the snapshot ID; repeated runs are identical
#   3. common random numbers are shared across candidate lineups and both sides
#   4. QB-to-pass-catcher and game-script correlation are modelled
#   5. P(win) responds monotonically to a strictly better lineup

SEED = 735806


def player(
    player_id: str,
    position: str = "WR",
    *,
    mean: float = 12.0,
    sigma: float = 5.0,
    skew: float = 0.4,
    nfl_team: str | None = None,
    game_id: str | None = None,
) -> SimPlayer:
    return SimPlayer(
        player_id=player_id,
        position=position,
        mean=mean,
        sigma=sigma,
        skew=skew,
        nfl_team=nfl_team,
        game_id=game_id,
    )


def a_lineup(prefix: str, means: list[float]) -> list[SimPlayer]:
    positions = ["QB", "RB", "RB", "WR", "WR", "TE", "K", "DEF", "IDP"]
    return [
        player(f"{prefix}-{i}", positions[i % len(positions)], mean=m)
        for i, m in enumerate(means)
    ]


DP_MEANS = [21, 12, 10, 15, 13, 9, 8, 7, 9]
OPP_MEANS = [20, 11, 11, 14, 12, 10, 8, 8, 8]


# --- acceptance criterion 1: a 10k-trial sim returns P(win) + summary stats ---


def test_sim_returns_p_win_and_summary_stats_over_ten_thousand_trials():
    result = simulate_head_to_head(
        a_lineup("dp", DP_MEANS), a_lineup("opp", OPP_MEANS), rng_seed=SEED
    )
    assert result.n_trials == DEFAULT_TRIALS == 10_000
    assert 0.0 <= result.p_win <= 1.0
    assert 0.0 <= result.p_tie <= 1.0
    for side in (result.dead_parrots, result.opponent):
        assert side.p10 < side.p50 < side.p90
        assert side.stdev > 0.0
    # Dead Parrots mean edge is small but positive here
    assert result.mean_margin == pytest.approx(
        result.dead_parrots.mean - result.opponent.mean, abs=0.02
    )
    assert result.p_win > 0.5


def test_side_summary_mean_tracks_the_sum_of_slot_means():
    result = simulate_head_to_head(
        a_lineup("dp", DP_MEANS), a_lineup("opp", OPP_MEANS), rng_seed=SEED
    )
    assert result.dead_parrots.mean == pytest.approx(sum(DP_MEANS), abs=0.4)
    assert result.opponent.mean == pytest.approx(sum(OPP_MEANS), abs=0.4)


# --- acceptance criterion 2: identical inputs + seed -> identical output ------


def test_same_inputs_and_seed_produce_identical_output():
    dp, opp = a_lineup("dp", DP_MEANS), a_lineup("opp", OPP_MEANS)
    first = simulate_head_to_head(dp, opp, rng_seed=SEED)
    second = simulate_head_to_head(dp, opp, rng_seed=SEED)
    assert dataclasses.astuple(first) == dataclasses.astuple(second)


def test_a_different_seed_generally_moves_p_win():
    dp, opp = a_lineup("dp", DP_MEANS), a_lineup("opp", OPP_MEANS)
    p_a = simulate_head_to_head(dp, opp, rng_seed=1).p_win
    p_b = simulate_head_to_head(dp, opp, rng_seed=2).p_win
    assert p_a != p_b
    assert abs(p_a - p_b) < 0.05  # ...but only by sampling noise


# --- acceptance criterion 3: common random numbers --------------------------


def test_a_player_is_drawn_the_same_whoever_it_lines_up_beside():
    # sample_lineup_totals on a concatenated lineup == elementwise sum of the
    # per-player runs: a slot's draws never depend on its lineup-mates.
    qb = player("qb1", "QB", mean=22.0, nfl_team="BUF", game_id="BUF-MIA")
    wr = player("wr1", "WR", mean=16.0, nfl_team="BUF", game_id="BUF-MIA")
    te = player("te1", "TE", mean=9.0, nfl_team="BUF", game_id="BUF-MIA")

    together = sample_lineup_totals([qb, wr, te], rng_seed=SEED, n_trials=2_000)
    apart = [
        sum(parts)
        for parts in zip(
            sample_lineup_totals([qb], rng_seed=SEED, n_trials=2_000),
            sample_lineup_totals([wr], rng_seed=SEED, n_trials=2_000),
            sample_lineup_totals([te], rng_seed=SEED, n_trials=2_000),
        )
    ]
    # equal to floating-point summation order (no *sampling* noise: a slot's
    # per-trial draw is byte-identical whether or not its lineup-mates are there)
    assert together == pytest.approx(apart, abs=1e-9, rel=0)


def test_swapping_one_slot_leaves_every_other_slot_and_the_opponent_noise_free():
    # Two candidate Dead Parrots lineups differing in exactly one slot, scored
    # against the same opponent. The per-trial difference in the Dead Parrots
    # total is exactly the swapped slot's contribution difference — the eight
    # shared slots contribute zero sampling noise.
    shared = a_lineup("dp", DP_MEANS)[:8]
    wr_old = player("swing", "WR", mean=11.0, nfl_team="KC", game_id="KC-LV")
    wr_new = player("swing", "WR", mean=17.0, nfl_team="KC", game_id="KC-LV")

    total_old = sample_lineup_totals([*shared, wr_old], rng_seed=SEED, n_trials=3_000)
    total_new = sample_lineup_totals([*shared, wr_new], rng_seed=SEED, n_trials=3_000)

    only_old = sample_lineup_totals([wr_old], rng_seed=SEED, n_trials=3_000)
    only_new = sample_lineup_totals([wr_new], rng_seed=SEED, n_trials=3_000)

    lineup_delta = [n - o for n, o in zip(total_new, total_old)]
    slot_delta = [n - o for n, o in zip(only_new, only_old)]
    assert lineup_delta == pytest.approx(slot_delta, abs=1e-9)
    # and because only the mean moved, that delta is a constant shift
    assert slot_delta == pytest.approx([6.0] * 3_000, abs=1e-9)


def test_common_random_numbers_hold_across_separate_sim_calls():
    # The optimizer (issue #11) calls simulate_head_to_head once per candidate.
    # A fixed opponent must yield a byte-identical opponent distribution every
    # call, so candidate-vs-candidate P(win) gaps are signal, not noise.
    opp = a_lineup("opp", OPP_MEANS)
    r1 = simulate_head_to_head(a_lineup("dp", DP_MEANS), opp, rng_seed=SEED)
    bumped = DP_MEANS.copy()
    bumped[3] += 4
    r2 = simulate_head_to_head(a_lineup("dp", bumped), opp, rng_seed=SEED)
    assert dataclasses.astuple(r1.opponent) == dataclasses.astuple(r2.opponent)


# --- acceptance criterion 4: correlation is modelled, not independent -------


def test_qb_to_pass_catcher_stack_widens_the_lineup_distribution():
    # Same three marginals; the only difference is whether the QB and his two
    # pass-catchers share their team's offensive factor.
    stack = [
        player("qb", "QB", mean=22.0, sigma=7.0, nfl_team="BUF", game_id="g1"),
        player("wr", "WR", mean=15.0, sigma=6.0, nfl_team="BUF", game_id="g1"),
        player("te", "TE", mean=9.0, sigma=4.0, nfl_team="BUF", game_id="g1"),
    ]
    independent = [dataclasses.replace(p, nfl_team=None, game_id=None) for p in stack]

    stack_sd = statistics.pstdev(
        sample_lineup_totals(stack, rng_seed=SEED, n_trials=6_000)
    )
    indep_sd = statistics.pstdev(
        sample_lineup_totals(independent, rng_seed=SEED, n_trials=6_000)
    )
    assert stack_sd > indep_sd * 1.1


def test_game_script_correlates_players_sharing_an_nfl_game():
    # Two opposing pass-catchers: same game -> positively correlated totals;
    # different games -> not.
    same_game = [
        player("dp_wr", "WR", mean=14.0, sigma=6.0, nfl_team="KC", game_id="KC-BUF"),
        player("opp_wr", "WR", mean=14.0, sigma=6.0, nfl_team="BUF", game_id="KC-BUF"),
    ]
    diff_games = [
        dataclasses.replace(same_game[0], game_id="KC-BUF"),
        dataclasses.replace(same_game[1], game_id="NYJ-NE"),
    ]

    def corr(pair: list[SimPlayer]) -> float:
        a = sample_lineup_totals([pair[0]], rng_seed=SEED, n_trials=6_000)
        b = sample_lineup_totals([pair[1]], rng_seed=SEED, n_trials=6_000)
        return statistics.correlation(a, b)

    assert corr(same_game) > 0.1
    assert abs(corr(diff_games)) < 0.05


def test_sharing_a_game_couples_the_two_sides_and_tightens_the_margin():
    # Dead Parrots' two WRs and the opponent's two WRs all sit in one NFL game
    # and load the same way on its factor, so the two sides' totals rise and
    # fall together. Positively-correlated scores have a lower-variance
    # difference, so the matchup margin is tighter than when the opponent pair
    # plays in a different game instead (their own mutual correlation is the
    # same either way, so it cancels — only the cross-side coupling moves).
    dp = a_lineup("dp", DP_MEANS)
    for i in (3, 4):
        dp[i] = dataclasses.replace(dp[i], sigma=9.0, nfl_team="KC", game_id="KC-BUF")

    opp_shared = a_lineup("opp", OPP_MEANS)
    opp_apart = a_lineup("opp", OPP_MEANS)
    for i in (3, 4):
        opp_shared[i] = dataclasses.replace(
            opp_shared[i], sigma=9.0, nfl_team="BUF", game_id="KC-BUF"
        )
        opp_apart[i] = dataclasses.replace(
            opp_apart[i], sigma=9.0, nfl_team="NYJ", game_id="NYJ-NE"
        )

    def margin_sd(opponent: list[SimPlayer]) -> float:
        dp_totals = sample_lineup_totals(dp, rng_seed=SEED, n_trials=8_000)
        opp_totals = sample_lineup_totals(opponent, rng_seed=SEED, n_trials=8_000)
        return statistics.pstdev([d - o for d, o in zip(dp_totals, opp_totals)])

    assert margin_sd(opp_shared) < margin_sd(opp_apart)


# --- acceptance criterion 5: monotonic response to a strictly better lineup --


def _balanced_matchup(dp_scale: float = 1.0) -> tuple[list[SimPlayer], list[SimPlayer]]:
    dp = a_lineup("dp", [m * dp_scale for m in DP_MEANS])
    opp = a_lineup("opp", OPP_MEANS)
    return dp, opp


def test_p_win_rises_when_one_slot_gets_strictly_better():
    dp, opp = _balanced_matchup()
    base = simulate_head_to_head(dp, opp, rng_seed=SEED).p_win

    better = list(dp)
    better[4] = dataclasses.replace(better[4], mean=better[4].mean + 5.0)
    raised = simulate_head_to_head(better, opp, rng_seed=SEED).p_win

    worse = list(dp)
    worse[4] = dataclasses.replace(worse[4], mean=worse[4].mean - 5.0)
    lowered = simulate_head_to_head(worse, opp, rng_seed=SEED).p_win

    assert lowered < base < raised


def test_p_win_is_monotonic_along_a_whole_ladder_of_improvements():
    _, opp = _balanced_matchup()
    probs = []
    for bump in (-6.0, -3.0, 0.0, 3.0, 6.0):
        dp = a_lineup("dp", [m + bump for m in DP_MEANS])
        probs.append(simulate_head_to_head(dp, opp, rng_seed=SEED).p_win)
    assert probs == sorted(probs)
    assert probs[0] < probs[-1]


def test_strictly_better_cannot_lower_p_win_even_trial_by_trial():
    dp, opp = _balanced_matchup()
    better = [dataclasses.replace(p, mean=p.mean + 2.0) for p in dp]
    base_dp = sample_lineup_totals(dp, rng_seed=SEED, n_trials=4_000)
    better_dp = sample_lineup_totals(better, rng_seed=SEED, n_trials=4_000)
    # every trial's total is lifted by the same total bump
    assert better_dp == pytest.approx(
        [t + 2.0 * len(dp) for t in base_dp], abs=1e-9
    )


# --- ADR-0002 support: variance helps the underdog, hurts the favourite ----


def test_lower_variance_helps_when_favoured_and_higher_variance_helps_when_behind():
    _, opp = _balanced_matchup()
    base_means = [m + 4 for m in DP_MEANS]  # clear favourite

    tight = a_lineup("dp", base_means)
    tight = [dataclasses.replace(p, sigma=2.0) for p in tight]
    swingy = [dataclasses.replace(p, sigma=9.0) for p in tight]

    fav_tight = simulate_head_to_head(tight, opp, rng_seed=SEED).p_win
    fav_swingy = simulate_head_to_head(swingy, opp, rng_seed=SEED).p_win
    assert fav_tight > fav_swingy  # favoured -> dampen variance

    dog_means = [m - 6 for m in DP_MEANS]  # clear underdog
    dog_tight = [dataclasses.replace(p, mean=dm, sigma=2.0) for p, dm in zip(tight, dog_means)]
    dog_swingy = [dataclasses.replace(p, sigma=9.0) for p in dog_tight]
    dog_p_tight = simulate_head_to_head(dog_tight, opp, rng_seed=SEED).p_win
    dog_p_swingy = simulate_head_to_head(dog_swingy, opp, rng_seed=SEED).p_win
    assert dog_p_swingy > dog_p_tight  # underdog -> embrace variance


# --- adapter from the projection model ------------------------------------


def test_sim_player_from_projection_reproduces_the_projection_median():
    games = tuple(
        PlayerGame(season=2026, week=w, actual_points=15.0 + (w % 3), expected_points=15.0)
        for w in range(1, 9)
    )
    proj = project(
        PlayerHistory(player_id="wr-x", position="WR", games=games),
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=10,
        rng_seed=SEED,
    )
    sp = sim_player_from_projection(proj, nfl_team="KC", game_id="KC-DEN")
    assert sp.mean == proj.components.mean_final
    assert sp.skew == proj.components.residual_skew

    # a one-player "lineup" the sim samples should land its P50 on the
    # projection's reported median (same shape, same sampler — ADR-0006)
    totals = sorted(sample_lineup_totals([sp], rng_seed=SEED, n_trials=10_000))
    sim_median = totals[len(totals) // 2]
    assert sim_median == pytest.approx(proj.projection, abs=0.6)


# --- guard rails ---------------------------------------------------------


def test_empty_lineup_is_rejected():
    with pytest.raises(ValueError):
        sample_lineup_totals([], rng_seed=SEED)


@pytest.mark.parametrize("bad", [0, -100])
def test_non_positive_trial_count_is_rejected(bad):
    with pytest.raises(ValueError):
        sample_lineup_totals([player("x")], rng_seed=SEED, n_trials=bad)
