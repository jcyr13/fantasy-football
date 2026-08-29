from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..simulation import DEFAULT_CORRELATION, DEFAULT_TRIALS, CorrelationSpec
from .evaluate import ContributionSampler
from .roster import Lineup, RosterPlayer

# Swing players (CONTEXT.md): the opponent's starters ranked by how much of the
# *matchup outcome variance* they drive. The outcome is the margin
# ``Dead Parrots total − opponent total``; a starter's swing contribution is how
# much the margin's variance drops when that starter is pinned to their mean
# (their randomness removed) while every other player's shared trial draws stay
# put — common random numbers again (ADR-0007). The measure captures a starter's
# own variance *and* its covariance with the rest of the matchup, so a boom/bust
# player in a shootout that also swings Dead Parrots' stack scores highest.

__all__ = [
    "SwingPlayer",
    "swing_players",
]


@dataclass(frozen=True)
class SwingPlayer:
    """One opponent starter's pull on the matchup outcome.

    ``variance_contribution`` is ``Var(margin) − Var(margin with this starter
    fixed at its mean)``, in points². ``variance_share`` divides that by
    ``Var(margin)``; shares need not sum to 1 because starters covary. A
    negative value (rare) means the starter *dampens* outcome variance rather
    than driving it. ``rank`` is 1 for the biggest swing.
    """

    player_id: str
    name: str
    position: str
    variance_contribution: float
    variance_share: float
    rank: int


def _pvariance(values: Sequence[float]) -> float:
    mean = math.fsum(values) / len(values)
    return math.fsum((v - mean) ** 2 for v in values) / len(values)


def swing_players(
    dead_parrots: Lineup,
    opponent: Sequence[RosterPlayer],
    *,
    rng_seed: int,
    correlation: CorrelationSpec = DEFAULT_CORRELATION,
    n_trials: int = DEFAULT_TRIALS,
) -> tuple[SwingPlayer, ...]:
    """Rank ``opponent``'s starters by their contribution to matchup-outcome
    variance, biggest first.

    Uses the same ``(rng_seed, correlation, n_trials)`` as the optimizer's
    head-to-head runs so the trial draws align.
    """
    if not opponent:
        raise ValueError("opponent lineup has no players")

    sampler = ContributionSampler(
        rng_seed=rng_seed, correlation=correlation, n_trials=n_trials
    )
    opp_contributions = [sampler.of(player.sim) for player in opponent]
    dp_totals = sampler.totals_for(dead_parrots.sims)
    opp_totals = sampler.totals_for([player.sim for player in opponent])
    margin = [dp - opp for dp, opp in zip(dp_totals, opp_totals)]
    var_margin = _pvariance(margin)

    scored: list[tuple[float, RosterPlayer]] = []
    for player, contribution in zip(opponent, opp_contributions):
        player_mean = math.fsum(contribution) / n_trials
        # Pin this starter to its mean: the opponent total loses (c_t − mean),
        # so the margin gains it back. Var of that pinned margin, differenced
        # against the real one, is the variance this starter was carrying.
        pinned_margin = [
            m + (c - player_mean) for m, c in zip(margin, contribution)
        ]
        contribution_to_variance = var_margin - _pvariance(pinned_margin)
        scored.append((contribution_to_variance, player))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(
        SwingPlayer(
            player_id=player.player_id,
            name=player.name,
            position=player.position,
            variance_contribution=value,
            variance_share=(value / var_margin) if var_margin > 0 else 0.0,
            rank=rank,
        )
        for rank, (value, player) in enumerate(scored, start=1)
    )
