from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ..simulation import (
    DEFAULT_CORRELATION,
    DEFAULT_TRIALS,
    CorrelationSpec,
    HeadToHeadResult,
    simulate_head_to_head,
)
from .evaluate import LineupEvaluation, evaluate_lineups
from .gap_drivers import GapDriver, gap_drivers
from .opponent import OpponentLineup
from .roster import Lineup, RosterPlayer, enumerate_lineups
from .slots import RIP_TIDE_SLOTS, LineupSlots
from .swing import SwingPlayer, swing_players

# The lineup optimizer (issue #11). Enumerate every legal lineup from the
# non-IR roster, score each against the opponent's likely lineup under common
# random numbers, and surface:
#
#   * max_p_win  — the lineup with the best P(win). The primary recommendation
#                  (ADR-0002). Safe-when-favored / boom-when-underdog falls out
#                  of the math, not a rule.
#   * max_ev     — the lineup with the most expected points, opponent ignored.
#   * floor      — the lineup with the best P10.
#   * ceiling    — the lineup with the best P90.
#   * threshold_rule — the alternative recommendation from the simpler
#                  favored→floor / underdog→ceiling rule, offered as a toggle,
#                  never the default (ADR-0002 "Considered Options").
#
# plus the gap-driver decomposition and swing-player ranking for the primary
# recommendation versus the opponent.

__all__ = [
    "DEFAULT_FAVORED_THRESHOLD",
    "DEFAULT_UNDERDOG_THRESHOLD",
    "OptimizerResult",
    "ThresholdRuleRecommendation",
    "optimize_lineups",
]

DEFAULT_FAVORED_THRESHOLD = 0.65
DEFAULT_UNDERDOG_THRESHOLD = 0.40

ThresholdBranch = Literal[
    "favored-optimize-floor",
    "underdog-optimize-ceiling",
    "coin-flip-optimize-median",
]


@dataclass(frozen=True)
class ThresholdRuleRecommendation:
    """What the favored→floor / underdog→ceiling toggle recommends instead.

    ``situation_p_win`` is the max-P(win) lineup's win probability — the read of
    how favored Dead Parrots are — compared against the two thresholds to pick
    ``branch``. ``evaluation`` is the lineup that branch points at (the floor,
    ceiling, or median lineup already computed in the sweep).
    """

    branch: ThresholdBranch
    evaluation: LineupEvaluation
    situation_p_win: float
    favored_threshold: float
    underdog_threshold: float


@dataclass(frozen=True)
class OptimizerResult:
    """Everything issue #11 reports for one matchup."""

    max_p_win: LineupEvaluation
    max_ev: LineupEvaluation
    floor: LineupEvaluation
    ceiling: LineupEvaluation
    median: LineupEvaluation
    threshold_rule: ThresholdRuleRecommendation
    gap_drivers: tuple[GapDriver, ...]
    swing_players: tuple[SwingPlayer, ...]
    opponent_assumption: str
    opponent_notes: tuple[str, ...]
    head_to_head: HeadToHeadResult
    evaluations: tuple[LineupEvaluation, ...]
    rng_seed: int

    @property
    def n_candidates(self) -> int:
        return len(self.evaluations)

    @property
    def recommendation(self) -> LineupEvaluation:
        """The primary recommendation: the max-P(win) lineup."""
        return self.max_p_win


def _argmax(
    evaluations: Sequence[LineupEvaluation],
    key,
) -> LineupEvaluation:
    """Highest ``key``, ties broken by the lineup's sorted player ids so the
    pick is deterministic across runs."""
    return max(
        evaluations,
        key=lambda ev: (key(ev), tuple(sorted(ev.lineup.player_ids))),
    )


def optimize_lineups(
    roster: Sequence[RosterPlayer],
    opponent: OpponentLineup | Sequence[RosterPlayer],
    *,
    rng_seed: int,
    slots: LineupSlots = RIP_TIDE_SLOTS,
    correlation: CorrelationSpec = DEFAULT_CORRELATION,
    n_trials: int = DEFAULT_TRIALS,
    favored_threshold: float = DEFAULT_FAVORED_THRESHOLD,
    underdog_threshold: float = DEFAULT_UNDERDOG_THRESHOLD,
) -> OptimizerResult:
    """Run the full optimizer for one matchup.

    ``roster`` is the Dead Parrots non-IR roster (IR filtered out by the
    caller). ``opponent`` is either an :class:`OpponentLineup` from
    :func:`build_opponent_lineup` (its assumption is carried onto the result) or
    a bare sequence of the opponent's ten starters.
    """
    if isinstance(opponent, OpponentLineup):
        opponent_players: Sequence[RosterPlayer] = opponent.players
        assumption = opponent.assumption
        opponent_notes = opponent.notes
    else:
        opponent_players = tuple(opponent)
        assumption = "provided"
        opponent_notes = ()

    opponent_sims = [p.sim for p in opponent_players]

    candidates = list(enumerate_lineups(roster, slots))
    if not candidates:
        raise ValueError("no legal lineup can be built from this roster")

    evaluations = evaluate_lineups(
        candidates,
        opponent_sims,
        rng_seed=rng_seed,
        correlation=correlation,
        n_trials=n_trials,
    )

    max_p_win = _argmax(evaluations, lambda ev: ev.p_win)
    max_ev = _argmax(evaluations, lambda ev: ev.expected_points)
    floor = _argmax(evaluations, lambda ev: ev.p10)
    ceiling = _argmax(evaluations, lambda ev: ev.p90)
    median = _argmax(evaluations, lambda ev: ev.p50)

    threshold_rule = _threshold_rule(
        situation_p_win=max_p_win.p_win,
        floor=floor,
        ceiling=ceiling,
        median=median,
        favored_threshold=favored_threshold,
        underdog_threshold=underdog_threshold,
    )

    recommended: Lineup = max_p_win.lineup
    head_to_head = simulate_head_to_head(
        recommended.sims,
        opponent_sims,
        rng_seed=rng_seed,
        correlation=correlation,
        n_trials=n_trials,
    )

    return OptimizerResult(
        max_p_win=max_p_win,
        max_ev=max_ev,
        floor=floor,
        ceiling=ceiling,
        median=median,
        threshold_rule=threshold_rule,
        gap_drivers=gap_drivers(recommended, opponent_players, slots=slots),
        swing_players=swing_players(
            recommended,
            opponent_players,
            rng_seed=rng_seed,
            correlation=correlation,
            n_trials=n_trials,
        ),
        opponent_assumption=assumption,
        opponent_notes=opponent_notes,
        head_to_head=head_to_head,
        evaluations=tuple(evaluations),
        rng_seed=rng_seed,
    )


def _threshold_rule(
    *,
    situation_p_win: float,
    floor: LineupEvaluation,
    ceiling: LineupEvaluation,
    median: LineupEvaluation,
    favored_threshold: float,
    underdog_threshold: float,
) -> ThresholdRuleRecommendation:
    """The simpler favored→floor / underdog→ceiling / else→median rule
    (methodology, ADR-0002 "Considered Options")."""
    if situation_p_win > favored_threshold:
        branch: ThresholdBranch = "favored-optimize-floor"
        evaluation = floor
    elif situation_p_win < underdog_threshold:
        branch = "underdog-optimize-ceiling"
        evaluation = ceiling
    else:
        branch = "coin-flip-optimize-median"
        evaluation = median
    return ThresholdRuleRecommendation(
        branch=branch,
        evaluation=evaluation,
        situation_p_win=situation_p_win,
        favored_threshold=favored_threshold,
        underdog_threshold=underdog_threshold,
    )
