from __future__ import annotations

from dataclasses import dataclass

from .inputs import LeagueState
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams

# Expected wins (methodology §4.2): for each past week, take Dead Parrots'
# actual score and compute the fraction of the other 11 teams it would have
# beaten that week; sum across weeks. Comparing that sum to *actual* wins
# exposes how much head-to-head schedule luck has helped or hurt the record
# (CONTEXT.md "Expected wins").

__all__ = ["ExpectedWins", "WeeklyExpectedWins", "expected_wins"]


@dataclass(frozen=True)
class WeeklyExpectedWins:
    """One completed week's contribution to the expected-wins total."""

    week: int
    dead_parrots_points: float
    opponents_scored: int
    opponents_beaten: float  # a tie counts as half a beaten opponent
    expected_wins: float  # opponents_beaten / opponents_scored


@dataclass(frozen=True)
class ExpectedWins:
    """Season-to-date expected wins against actual wins.

    ``luck = actual_wins - expected_wins``: positive means the head-to-head
    schedule has flattered the record, negative means it has robbed it.
    """

    expected_wins: float
    actual_wins: float
    luck: float
    weeks_counted: int
    weekly: tuple[WeeklyExpectedWins, ...]


def expected_wins(
    state: LeagueState, params: StrategyParams = DEFAULT_STRATEGY_PARAMS
) -> ExpectedWins:
    """Compute Dead Parrots' expected wins over ``state`` (methodology §4.2).

    Only weeks in which Dead Parrots have a recorded score count. Within such a
    week, only the other teams that also have a recorded score are ranked
    against (a team on bye that week, or a not-yet-scored week, is skipped).
    """
    dp = state.dead_parrots
    dp_points_by_week = dp.points_for_by_week

    weekly: list[WeeklyExpectedWins] = []
    raw_total = 0.0
    for week in sorted(dp_points_by_week):
        dp_points = dp_points_by_week[week]
        opp_points = [
            t.points_for_by_week[week]
            for t in state.other_teams
            if week in t.points_for_by_week
        ]
        if not opp_points:
            continue
        beaten = sum(1.0 for p in opp_points if dp_points > p) + sum(
            0.5 for p in opp_points if dp_points == p
        )
        # Accumulate the exact fraction; only the *reported* fields are rounded,
        # so per-week rounding never compounds into the season total.
        raw_total += beaten / len(opp_points)
        weekly.append(
            WeeklyExpectedWins(
                week=week,
                dead_parrots_points=dp_points,
                opponents_scored=len(opp_points),
                opponents_beaten=round(beaten, 6),
                expected_wins=round(beaten / len(opp_points), 6),
            )
        )

    total = round(raw_total, 6)
    actual = dp.actual_wins
    return ExpectedWins(
        expected_wins=total,
        actual_wins=actual,
        luck=round(actual - raw_total, 6),
        weeks_counted=len(weekly),
        weekly=tuple(weekly),
    )
