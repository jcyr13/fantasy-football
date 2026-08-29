from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from ..projection import cornish_fisher_unit, sample_quantile
from ..scoring import round_points
from .correlation import DEFAULT_CORRELATION, CorrelationSpec, loadings_for
from .marginals import SimPlayer

# The head-to-head Monte Carlo (issue #10):
#
#   (dead_parrots_lineup, opponent_lineup, correlation, rng_seed)
#     -> P(win) and summary stats, over 10,000 correlated trials.
#
# Win probability is the fraction of trials in which the Dead Parrots total
# strictly exceeds the opponent total (CONTEXT.md "Win probability").
#
# COMMON RANDOM NUMBERS. Every source of randomness is a *factor stream* — a
# deterministic list of ``n_trials`` standard-normal draws keyed by
# ``(rng_seed, factor)`` and nothing else (see :func:`_factor_stream`). A
# player's per-trial points are a fixed function of the streams for its own id,
# its NFL team, and its NFL game. So:
#
#   * swapping one slot in a candidate lineup leaves every other slot's per-trial
#     points untouched — lineup-vs-lineup comparisons carry no sampling noise;
#   * the opponent lineup is unchanged across all those candidates, so its
#     per-trial totals are identical every time;
#   * both sides draw from the same ``rng_seed`` namespace, so a shared NFL game
#     couples them rather than two independent RNGs.
#
# This is acceptance criterion 3. It holds across separate
# :func:`simulate_head_to_head` calls, which is how the lineup optimizer (issue
# #11) will use it. See ADR-0007.

DEFAULT_TRIALS = 10_000

# Unit separator — keeps the composite stream key unambiguous without a hash.
_KEY_SEP = "\x1f"


@lru_cache(maxsize=256)
def _factor_stream(seed_key: str, n_trials: int) -> tuple[float, ...]:
    """``n_trials`` i.i.d. standard-normal draws for one factor.

    Seeded from a string so it is stable across processes (``random.Random``
    hashes str/bytes seeds with SHA-512). Cached so re-running the sim with the
    same seed reuses streams — a full matchup's ~50 distinct keys fit many times
    over. The issue #11 optimizer enumerates far more candidates than that
    against one opponent, so it should hoist the opponent's
    :func:`sample_lineup_totals` result rather than rely on this cache to hold
    the shared streams across a whole enumeration.
    """
    rng = random.Random(seed_key)
    return tuple(rng.gauss(0.0, 1.0) for _ in range(n_trials))


def _stream_for(
    rng_seed: int, factor_kind: str, factor_key: str, n_trials: int
) -> tuple[float, ...]:
    """The standard-normal stream for one ``(seed, factor kind, factor id)``."""
    return _factor_stream(
        f"{rng_seed}{_KEY_SEP}{factor_kind}{_KEY_SEP}{factor_key}", n_trials
    )


def _shared_factor_keys(player: SimPlayer) -> tuple[str, str]:
    """This player's ``(team, game)`` factor ids.

    A known NFL team / game gives a *shared* id (everyone on that team's offence,
    everyone in that game, draws the same stream); an unknown one falls back to
    a per-player id so the player shares that factor with no one and its
    marginal is unchanged.
    """
    team_key = (
        f"team{_KEY_SEP}{player.nfl_team}"
        if player.nfl_team is not None
        else f"team-solo{_KEY_SEP}{player.player_id}"
    )
    game_key = (
        f"game{_KEY_SEP}{player.game_id}"
        if player.game_id is not None
        else f"game-solo{_KEY_SEP}{player.player_id}"
    )
    return team_key, game_key


@dataclass(frozen=True)
class SideSummary:
    """Distribution of one lineup's weekly total across the trials."""

    mean: float
    p10: float
    p50: float
    p90: float
    stdev: float


@dataclass(frozen=True)
class HeadToHeadResult:
    """The sim's answer for one matchup.

    ``p_win`` is P(Dead Parrots total > opponent total); ``p_tie`` the fraction
    of exact ties (vanishingly rare with continuous marginals, surfaced for
    completeness). ``mean_margin`` is E[Dead Parrots − opponent].
    """

    p_win: float
    p_tie: float
    mean_margin: float
    dead_parrots: SideSummary
    opponent: SideSummary
    n_trials: int
    rng_seed: int


def sample_lineup_totals(
    lineup: Sequence[SimPlayer],
    *,
    rng_seed: int,
    correlation: CorrelationSpec = DEFAULT_CORRELATION,
    n_trials: int = DEFAULT_TRIALS,
) -> list[float]:
    """Per-trial weekly total for one lineup under the correlation model.

    The common-random-numbers seam: the returned list is a pure function of
    ``(lineup members, rng_seed, correlation, n_trials)`` and each player's
    contribution depends only on its own / its team's / its game's factor
    streams. Summing two independent calls' outputs elementwise therefore equals
    the output of one call on the concatenated lineup — a player is drawn the
    same whoever it lines up beside.
    """
    if not lineup:
        raise ValueError("lineup has no players")
    if n_trials <= 0:
        raise ValueError(f"n_trials must be positive: {n_trials!r}")

    totals = [0.0] * n_trials
    for player in lineup:
        coef = loadings_for(player.position, correlation)
        team_key, game_key = _shared_factor_keys(player)
        team_stream = _stream_for(rng_seed, "team", team_key, n_trials)
        game_stream = _stream_for(rng_seed, "game", game_key, n_trials)
        idio_stream = _stream_for(rng_seed, "idio", player.player_id, n_trials)

        mean, sigma, skew = player.mean, player.sigma, player.skew
        team_c, game_c, idio_c = coef.team_coef, coef.game_coef, coef.idio_coef
        for t in range(n_trials):
            z = team_c * team_stream[t] + game_c * game_stream[t] + idio_c * idio_stream[t]
            totals[t] += mean + cornish_fisher_unit(z, skew) * sigma
    return totals


def simulate_head_to_head(
    dead_parrots_lineup: Sequence[SimPlayer],
    opponent_lineup: Sequence[SimPlayer],
    *,
    rng_seed: int,
    correlation: CorrelationSpec = DEFAULT_CORRELATION,
    n_trials: int = DEFAULT_TRIALS,
) -> HeadToHeadResult:
    """Run the head-to-head Monte Carlo for one matchup.

    Both lineups are sampled from the same ``rng_seed`` namespace (common random
    numbers), so a strictly better Dead Parrots lineup can only raise ``p_win``
    and a shared NFL game correlates the two sides.
    """
    dp_totals = sample_lineup_totals(
        dead_parrots_lineup,
        rng_seed=rng_seed,
        correlation=correlation,
        n_trials=n_trials,
    )
    opp_totals = sample_lineup_totals(
        opponent_lineup,
        rng_seed=rng_seed,
        correlation=correlation,
        n_trials=n_trials,
    )

    wins = sum(1 for dp, opp in zip(dp_totals, opp_totals) if dp > opp)
    ties = sum(1 for dp, opp in zip(dp_totals, opp_totals) if dp == opp)

    dead_parrots = summarise_side(dp_totals)
    opponent = summarise_side(opp_totals)
    return HeadToHeadResult(
        p_win=wins / n_trials,
        p_tie=ties / n_trials,
        # mean(a - b) == mean(a) - mean(b) exactly, so derive it from the
        # rounded side means and the documented identity holds to the cent.
        mean_margin=round_points(dead_parrots.mean - opponent.mean),
        dead_parrots=dead_parrots,
        opponent=opponent,
        n_trials=n_trials,
        rng_seed=rng_seed,
    )


# --- summary stats ------------------------------------------------------


def summarise_side(totals: Sequence[float]) -> SideSummary:
    """One side's per-trial totals reduced to a rounded :class:`SideSummary`.

    Public so the issue #11 optimizer scores candidate lineups with the *same*
    reduction ``simulate_head_to_head`` uses — one sort, ``math.fsum`` mean,
    linear-interpolation quantiles, ``round_points`` throughout — rather than a
    second copy that could drift (ADR-0008 §3).
    """
    ordered = sorted(totals)
    mean = math.fsum(ordered) / len(ordered)
    variance = math.fsum((x - mean) ** 2 for x in ordered) / len(ordered)
    return SideSummary(
        mean=round_points(mean),
        p10=round_points(sample_quantile(ordered, 0.10)),
        p50=round_points(sample_quantile(ordered, 0.50)),
        p90=round_points(sample_quantile(ordered, 0.90)),
        stdev=round_points(math.sqrt(max(variance, 0.0))),
    )
