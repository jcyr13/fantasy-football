from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..simulation import (
    DEFAULT_CORRELATION,
    DEFAULT_TRIALS,
    CorrelationSpec,
    SimPlayer,
    sample_lineup_totals,
    summarise_side,
)
from .roster import Lineup

# Scoring every candidate lineup against the one opponent lineup, under common
# random numbers (ADR-0007, ADR-0008).
#
# ``sample_lineup_totals`` guarantees a lineup's per-trial totals are the
# elementwise sum of its players' individual per-trial contributions — a player
# is drawn the same whoever it lines up beside. So we sample each distinct
# player *once* and add up the ten arrays per candidate, which reproduces
# ``simulate_head_to_head`` exactly (same seed, same trial count, same summing
# order, same :func:`summarise_side` reduction) while sampling ~20 players
# instead of ~20 × thousands-of-candidates.

__all__ = [
    "ContributionSampler",
    "LineupEvaluation",
    "evaluate_lineups",
    "sum_contributions",
]


@dataclass(frozen=True)
class LineupEvaluation:
    """One candidate lineup's numbers, all rounded like every points figure in
    the app.

    ``p_win`` is P(this lineup's weekly total > the opponent's), estimated over
    the shared trials. ``expected_points`` / ``p10`` / ``p50`` / ``p90`` describe
    the lineup's own weekly-total distribution.
    """

    lineup: Lineup
    p_win: float
    expected_points: float
    p10: float
    p50: float
    p90: float


def sum_contributions(
    contributions: Sequence[Sequence[float]], n_trials: int
) -> list[float]:
    """Elementwise sum of per-player contribution arrays, accumulated in the
    given order — the order ``sample_lineup_totals`` would add them in, so the
    result is float-identical to one ``sample_lineup_totals`` call on the whole
    lineup."""
    totals = [0.0] * n_trials
    for contribution in contributions:
        for trial in range(n_trials):
            totals[trial] += contribution[trial]
    return totals


class ContributionSampler:
    """Caches each player's per-trial contribution stream for one
    ``(rng_seed, correlation, n_trials)``.

    The common-random-numbers seam for the whole optimizer: a player sampled
    here contributes identically to every lineup it appears in and to both
    sides, so candidate-vs-candidate gaps are signal, not sampling noise.
    """

    def __init__(
        self,
        *,
        rng_seed: int,
        correlation: CorrelationSpec = DEFAULT_CORRELATION,
        n_trials: int = DEFAULT_TRIALS,
    ) -> None:
        self.rng_seed = rng_seed
        self.correlation = correlation
        self.n_trials = n_trials
        self._cache: dict[str, list[float]] = {}

    def of(self, player: SimPlayer) -> list[float]:
        cached = self._cache.get(player.player_id)
        if cached is None:
            cached = sample_lineup_totals(
                [player],
                rng_seed=self.rng_seed,
                correlation=self.correlation,
                n_trials=self.n_trials,
            )
            self._cache[player.player_id] = cached
        return cached

    def totals_for(self, players: Sequence[SimPlayer]) -> list[float]:
        """Per-trial totals for a lineup, summed in the given player order."""
        return sum_contributions([self.of(p) for p in players], self.n_trials)


def evaluate_lineups(
    candidates: Iterable[Lineup],
    opponent: Sequence[SimPlayer],
    *,
    rng_seed: int,
    correlation: CorrelationSpec = DEFAULT_CORRELATION,
    n_trials: int = DEFAULT_TRIALS,
) -> list[LineupEvaluation]:
    """Evaluate every candidate lineup against ``opponent`` under one seed.

    The opponent's per-trial totals are computed once and reused for all
    candidates.
    """
    if not opponent:
        raise ValueError("opponent lineup has no players")

    sampler = ContributionSampler(
        rng_seed=rng_seed, correlation=correlation, n_trials=n_trials
    )
    opponent_totals = sampler.totals_for(opponent)

    evaluations: list[LineupEvaluation] = []
    for lineup in candidates:
        lineup_totals = sampler.totals_for(lineup.sims)
        wins = sum(
            1 for own, opp in zip(lineup_totals, opponent_totals) if own > opp
        )
        summary = summarise_side(lineup_totals)
        evaluations.append(
            LineupEvaluation(
                lineup=lineup,
                p_win=wins / n_trials,
                expected_points=summary.mean,
                p10=summary.p10,
                p50=summary.p50,
                p90=summary.p90,
            )
        )
    return evaluations
