from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..lineup import LineupSlots, can_field_legal_lineup, role_of
from .inputs import ByePlayer, LeagueState
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams

# The bye-week crunch map (methodology §4.4): for each upcoming week, count Dead
# Parrots *starters* on bye by position and grade the week.
#
#   warn      2 starters on bye at one position (usually coverable from the
#             bench with a downgrade)
#   critical  3+ at one position, OR any week a legal healthy lineup cannot be
#             fielded at all (forces a waiver move now, not later)
#
# The count is over starters; the "can a legal lineup be fielded" check draws
# from the whole roster minus players on bye that week minus players ruled out
# for the season.

__all__ = [
    "ByeCrunchGrade",
    "ByeCrunchMap",
    "PositionByeCount",
    "WeekByeCrunch",
    "bye_crunch_map",
]

ByeCrunchGrade = Literal["ok", "warn", "critical"]


@dataclass(frozen=True)
class PositionByeCount:
    """Starters on bye at one role in one week (only roles with >= 1 appear)."""

    role: str
    starters_on_bye: int
    starter_names: tuple[str, ...]


@dataclass(frozen=True)
class WeekByeCrunch:
    """One upcoming week's bye picture and its grade."""

    week: int
    grade: ByeCrunchGrade
    per_position: tuple[PositionByeCount, ...]
    max_at_one_position: int
    can_field_legal_lineup: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ByeCrunchMap:
    """The grade for every upcoming regular-season week."""

    weeks: tuple[WeekByeCrunch, ...]

    @property
    def worst_grade(self) -> ByeCrunchGrade:
        order: dict[ByeCrunchGrade, int] = {"ok": 0, "warn": 1, "critical": 2}
        worst: ByeCrunchGrade = "ok"
        for week in self.weeks:
            if order[week.grade] > order[worst]:
                worst = week.grade
        return worst

    def week(self, week: int) -> WeekByeCrunch:
        try:
            return next(w for w in self.weeks if w.week == week)
        except StopIteration:
            raise KeyError(f"week {week} is not in the map") from None


def _on_bye(player: ByePlayer, week: int) -> bool:
    return player.bye_week == week


def _grade_week(
    week: int,
    roster: tuple[ByePlayer, ...],
    slots: LineupSlots,
    params: StrategyParams,
) -> WeekByeCrunch:
    by_role: dict[str, list[str]] = {}
    for player in roster:
        if player.is_starter and _on_bye(player, week):
            by_role.setdefault(role_of(player.position), []).append(player.name)

    per_position = tuple(
        PositionByeCount(
            role=role,
            starters_on_bye=len(names),
            starter_names=tuple(sorted(names)),
        )
        for role, names in sorted(by_role.items())
    )
    max_at_one = max((p.starters_on_bye for p in per_position), default=0)

    available_pool = [
        p for p in roster if p.available and not _on_bye(p, week)
    ]
    can_field = can_field_legal_lineup(available_pool, slots)

    reasons: list[str] = []
    grade: ByeCrunchGrade
    if not can_field:
        grade = "critical"
        reasons.append(
            "No legal healthy lineup can be fielded this week from the "
            "non-bye, available roster."
        )
    elif max_at_one >= params.bye_crunch_critical_count:
        grade = "critical"
        worst = max(per_position, key=lambda p: p.starters_on_bye)
        reasons.append(
            f"{worst.starters_on_bye} {worst.role} starters on bye "
            f"({', '.join(worst.starter_names)})."
        )
    elif max_at_one >= params.bye_crunch_warn_count:
        grade = "warn"
        for p in per_position:
            if p.starters_on_bye >= params.bye_crunch_warn_count:
                reasons.append(
                    f"{p.starters_on_bye} {p.role} starters on bye "
                    f"({', '.join(p.starter_names)})."
                )
    else:
        grade = "ok"

    return WeekByeCrunch(
        week=week,
        grade=grade,
        per_position=per_position,
        max_at_one_position=max_at_one,
        can_field_legal_lineup=can_field,
        reasons=tuple(reasons),
    )


def bye_crunch_map(
    state: LeagueState, params: StrategyParams = DEFAULT_STRATEGY_PARAMS
) -> ByeCrunchMap:
    """Grade every upcoming regular-season week for Dead Parrots (methodology
    §4.4).

    "Upcoming" is ``state.current_week`` through ``state.regular_season_weeks``
    inclusive. Weeks with no roster player on bye and a fieldable lineup grade
    ``ok``.
    """
    weeks = tuple(
        _grade_week(week, state.dead_parrots_roster, state.lineup_slots, params)
        for week in range(state.current_week, state.regular_season_weeks + 1)
    )
    return ByeCrunchMap(weeks=weeks)
