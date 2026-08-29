from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..projection import sample_quantile
from ..scoring import round_points
from ..simulation import (
    DEFAULT_CORRELATION,
    DEFAULT_TRIALS,
    CorrelationSpec,
    SimPlayer,
    sample_lineup_totals,
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
# order) while sampling ~20 players instead of ~20 × thousands-of-candidates.

__all__ = [
    "LineupEvaluation",
    "evaluate_lineups",
    "summarise_totals",
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


def summarise_totals(totals: Sequence[float]) -> tuple[float, float, float, float]:
    """``(mean, p10, p50, p90)`` of a per-trial total series, computed exactly as
    :func:`deadparrots.simulation.montecarlo._summarise` does it — sorted once,
    ``math.fsum`` mean, linear-interpolation quantiles — so an evaluation's
    numbers match a full ``simulate_head_to_head`` on the same lineup."""
    ordered = sorted(totals)
    mean = math.fsum(ordered) / len(ordered)
    return (
        mean,
        sample_quantile(ordered, 0.10),
        sample_quantile(ordered, 0.50),
        sample_quantile(ordered, 0.90),
    )


def _sum_contributions(
    contributions: Sequence[Sequence[float]], n_trials: int
) -> list[float]:
    """Elementwise sum of per-player contribution arrays, accumulated in the
    given order (the order ``sample_lineup_totals`` would add them in)."""
    totals = [0.0] * n_trials
    for contribution in contributions:
        for trial in range(n_trials):
            totals[trial] += contribution[trial]
    return totals


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
    candidates, so candidate-vs-candidate ``p_win`` gaps are signal, not
    sampling noise.
    """
    if not opponent:
        raise ValueError("opponent lineup has no players")

    contribution_cache: dict[str, list[float]] = {}

    def contribution_of(player: SimPlayer) -> list[float]:
        cached = contribution_cache.get(player.player_id)
        if cached is None:
            cached = sample_lineup_totals(
                [player],
                rng_seed=rng_seed,
                correlation=correlation,
                n_trials=n_trials,
            )
            contribution_cache[player.player_id] = cached
        return cached

    opponent_totals = _sum_contributions(
        [contribution_of(p) for p in opponent], n_trials
    )

    evaluations: list[LineupEvaluation] = []
    for lineup in candidates:
        lineup_totals = _sum_contributions(
            [contribution_of(p) for p in lineup.sims], n_trials
        )
        wins = sum(
            1 for own, opp in zip(lineup_totals, opponent_totals) if own > opp
        )
        mean, p10, p50, p90 = summarise_totals(lineup_totals)
        evaluations.append(
            LineupEvaluation(
                lineup=lineup,
                p_win=wins / n_trials,
                expected_points=round_points(mean),
                p10=round_points(p10),
                p50=round_points(p50),
                p90=round_points(p90),
            )
        )
    return evaluations
