"""RIP TIDE head-to-head Monte Carlo simulation (issue #10; methodology §3.9).

``simulate_head_to_head(dead_parrots_lineup, opponent_lineup, ...)`` runs 10,000
correlated trials over two lineups' marginal weekly-point distributions and
returns ``P(win)`` plus summary stats. The marginals are :class:`SimPlayer`
records (the same Cornish-Fisher shape the projection model reports, ADR-0006);
the joint is a linear factor model (:mod:`correlation`) covering
QB-to-pass-catcher stacks and game script.

Every draw is a factor stream keyed only by ``rng_seed`` and a stable id, so
common random numbers hold across candidate lineups and both sides
(:func:`sample_lineup_totals` is the seam). The seed itself comes from the
weekly snapshot ID via :func:`seed_from_snapshot_id`. See ADR-0007.
"""

from __future__ import annotations

from .correlation import (
    DEFAULT_CORRELATION,
    CorrelationSpec,
    LatentLoadings,
    loadings_for,
    role_of,
)
from .marginals import SimPlayer, sim_player_from_projection
from .montecarlo import (
    DEFAULT_TRIALS,
    HeadToHeadResult,
    SideSummary,
    sample_lineup_totals,
    simulate_head_to_head,
    summarise_side,
)
from .seed import seed_from_snapshot_id

__all__ = [
    "DEFAULT_CORRELATION",
    "DEFAULT_TRIALS",
    "CorrelationSpec",
    "HeadToHeadResult",
    "LatentLoadings",
    "SideSummary",
    "SimPlayer",
    "loadings_for",
    "role_of",
    "sample_lineup_totals",
    "seed_from_snapshot_id",
    "sim_player_from_projection",
    "simulate_head_to_head",
    "summarise_side",
]
