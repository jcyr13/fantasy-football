from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from ..projection import decay_weights, weighted_mean
from .inputs import LeagueState
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams

# Team strength (methodology §4.1): Dead Parrots' rolling points-for,
# exponentially decay-weighted with a ~4-week half-life, expressed as a
# percentile against the other 11 teams' identically-computed values. The
# health signal — deliberately *not* win/loss record (CONTEXT.md "Team
# strength").

__all__ = ["TeamStrength", "TeamStrengthValue", "team_strength"]


@dataclass(frozen=True)
class TeamStrengthValue:
    """One team's decay-weighted points-for and where it lands in the league."""

    team_id: str
    team_name: str
    is_dead_parrots: bool
    decay_weighted_points_for: float
    weeks_counted: int
    rank: int  # 1 = highest decay-weighted points-for in the league


@dataclass(frozen=True)
class TeamStrength:
    """The team-strength read for Dead Parrots.

    ``percentile`` is Dead Parrots' standing among **the other 11 teams** only
    (0–100): the share of them with a strictly lower decay-weighted points-for
    plus half the share tied, the usual percentile-rank convention. ``league``
    carries every team's value in rank order for the UI drill-down — the
    "numbers behind it" the signal must show.
    """

    decay_weighted_points_for: float
    percentile: float
    weeks_counted: int
    half_life_weeks: float
    league: tuple[TeamStrengthValue, ...]

    @property
    def dead_parrots_rank(self) -> int:
        return next(v.rank for v in self.league if v.is_dead_parrots)


class _TeamValue(NamedTuple):
    """A team's decay-weighted points-for before it is ranked into the league
    table — read by name, never by position."""

    team_id: str
    team_name: str
    is_dead_parrots: bool
    decay_weighted_points_for: float
    weeks_counted: int


def _decay_weighted_points_for(series: list[float], half_life_weeks: float) -> float:
    """Decay-weighted mean of a team's completed-week points-for (oldest →
    newest). No completed weeks yet ⇒ 0.0 (every team is then equal and the
    percentile is the tie midpoint)."""
    if not series:
        return 0.0
    weights = decay_weights(len(series), half_life_weeks)
    return weighted_mean(series, weights)


def _percentile_rank(value: float, others: list[float]) -> float:
    """Percentile rank of ``value`` against ``others`` (0–100), counting a tie
    as half. Empty ``others`` ⇒ 50.0."""
    if not others:
        return 50.0
    below = sum(1 for o in others if o < value)
    equal = sum(1 for o in others if o == value)
    return 100.0 * (below + 0.5 * equal) / len(others)


def team_strength(
    state: LeagueState, params: StrategyParams = DEFAULT_STRATEGY_PARAMS
) -> TeamStrength:
    """Compute Dead Parrots' team strength over ``state`` (methodology §4.1)."""
    half_life = params.team_strength_decay_half_life_weeks

    values = [
        _TeamValue(
            team_id=team.team_id,
            team_name=team.team_name,
            is_dead_parrots=team.is_dead_parrots,
            decay_weighted_points_for=_decay_weighted_points_for(
                team.points_for_series(), half_life
            ),
            weeks_counted=len(team.weekly_scores),
        )
        for team in state.teams
    ]

    ordered = sorted(
        values, key=lambda v: (-v.decay_weighted_points_for, v.team_id)
    )
    league = tuple(
        TeamStrengthValue(
            team_id=v.team_id,
            team_name=v.team_name,
            is_dead_parrots=v.is_dead_parrots,
            decay_weighted_points_for=round(v.decay_weighted_points_for, 2),
            weeks_counted=v.weeks_counted,
            rank=rank,
        )
        for rank, v in enumerate(ordered, start=1)
    )

    dp = next(v for v in values if v.is_dead_parrots)
    others = [v.decay_weighted_points_for for v in values if not v.is_dead_parrots]
    return TeamStrength(
        decay_weighted_points_for=round(dp.decay_weighted_points_for, 2),
        percentile=round(_percentile_rank(dp.decay_weighted_points_for, others), 6),
        weeks_counted=dp.weeks_counted,
        half_life_weeks=half_life,
        league=league,
    )
