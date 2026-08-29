from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

# The scoring engine's input and output vocabulary (spec issue #1, "Scoring
# engine"; ticket #4). ``StatRow`` is the one shape the
# scoring function consumes: a player-week (or team-week, for DEF) tagged with
# the scoring unit it belongs to and a flat mapping of canonical stat keys to
# counts. Anything that can be turned into ``StatRow`` objects can be scored,
# which keeps the engine free of any knowledge of nflverse column names or I/O.


class ScoringUnit(StrEnum):
    """Which rule set a row is scored under.

    ``INDIVIDUAL_DEFENSE`` is the RIP TIDE "D" slot — a single defender scored on
    their own tackles, takeaways, and scores. It is a distinct surface from
    ``TEAM_DEFENSE`` (spec issue #1, "IDP / D slot"); the two are never mixed for
    one entity-week.
    """

    OFFENSE = "offense"
    KICKER = "kicker"
    TEAM_DEFENSE = "team_defense"
    INDIVIDUAL_DEFENSE = "individual_defense"


# Canonical stat keys the engine understands, per unit. A row may omit any key
# (treated as 0) but may not carry an unknown one — that is a caller bug and the
# engine raises rather than silently dropping points.

OFFENSE_STATS: frozenset[str] = frozenset(
    {
        "passing_yards",
        "passing_touchdowns",
        "interceptions_thrown",
        "sacks_taken",
        "two_point_conversions",
        "rushing_yards",
        "rushing_touchdowns",
        "receiving_yards",
        "receiving_touchdowns",
        "return_yards",
        "fumbles_lost",
        # RIP TIDE scores individual defensive plays for *any* player who records
        # one, not only the D slot — an offensive player who makes a tackle after
        # a turnover is credited. (The D-slot IDP surface proper is ticket #5.)
        "tackle_solo",
        "tackle_assist",
        "passes_defended",
    }
)

KICKER_STATS: frozenset[str] = frozenset(
    {
        "fg_made_0_19",
        "fg_made_20_29",
        "fg_made_30_39",
        "fg_made_40_49",
        "fg_made_50_plus",
        "fg_missed_0_19",
        "pat_made",
        "pat_missed",
        # A kicker who makes a tackle on the return is credited the same
        # individual-defense points as anyone else (see OFFENSE_STATS).
        "tackle_solo",
        "tackle_assist",
        "passes_defended",
    }
)

TEAM_DEFENSE_STATS: frozenset[str] = frozenset(
    {
        "sacks",
        "interceptions",
        "fumble_recoveries",
        "defensive_touchdowns",
        "safeties",
        "blocked_kicks",
        "tackles_for_loss",
        "return_yards",
        "points_allowed",
    }
)

# The "D" slot. Solo/assist tackles and passes defended share their canonical
# keys and values with offense/kicker; the rest (takeaways, scores, blocked
# kicks, TFL, and the defender's own interception/fumble-return yardage) are what
# makes this a surface of its own. ``turnover_return_yards`` is kept distinct
# from offense's kick/punt ``return_yards`` — the spec lists it as its own
# category — and ``forced_fumbles`` is unique to IDP, where team DEF only scores
# the recovery.
INDIVIDUAL_DEFENSE_STATS: frozenset[str] = frozenset(
    {
        "tackle_solo",
        "tackle_assist",
        "passes_defended",
        "sacks",
        "interceptions",
        "forced_fumbles",
        "fumble_recoveries",
        "defensive_touchdowns",
        "safeties",
        "blocked_kicks",
        "tackles_for_loss",
        "turnover_return_yards",
    }
)

STATS_BY_UNIT: Mapping[ScoringUnit, frozenset[str]] = {
    ScoringUnit.OFFENSE: OFFENSE_STATS,
    ScoringUnit.KICKER: KICKER_STATS,
    ScoringUnit.TEAM_DEFENSE: TEAM_DEFENSE_STATS,
    ScoringUnit.INDIVIDUAL_DEFENSE: INDIVIDUAL_DEFENSE_STATS,
}


PlayerWeekKey = tuple[str, int, int]
"""``(entity_id, season, week)`` — the identity of a scored row."""


class UnknownStatError(ValueError):
    """A ``StatRow`` carried a stat key the engine does not recognise."""

    def __init__(self, unit: ScoringUnit, unknown: list[str]) -> None:
        self.unit = unit
        self.unknown = unknown
        super().__init__(
            f"{unit.value}: unknown stat key(s): {', '.join(sorted(unknown))}"
        )


@dataclass(frozen=True)
class StatRow:
    """One player-week (or team-week) of raw counting stats to be scored.

    ``entity_id`` is the nflverse ``player_id`` for offense, kickers, and
    individual defenders, and the team abbreviation for ``TEAM_DEFENSE``.
    ``stats`` holds canonical keys from the unit's vocabulary; missing keys
    count as 0.
    """

    entity_id: str
    season: int
    week: int
    unit: ScoringUnit
    stats: Mapping[str, float] = field(default_factory=dict)
    label: str | None = None

    def __post_init__(self) -> None:
        allowed = STATS_BY_UNIT[self.unit]
        unknown = [key for key in self.stats if key not in allowed]
        if unknown:
            raise UnknownStatError(self.unit, unknown)

    @property
    def key(self) -> PlayerWeekKey:
        return (self.entity_id, self.season, self.week)

    def stat(self, name: str) -> float:
        """The value of ``name``, or 0.0 if the row does not carry it."""
        return float(self.stats.get(name, 0.0))


@dataclass(frozen=True)
class ScoredPlayerWeek:
    """The engine's output for one row: the total plus a component breakdown.

    ``points`` is rounded to two decimal places (half-up) to match how Yahoo
    reports a player's weekly fantasy points. ``breakdown`` keeps the exact
    unrounded contribution of each scoring component, for the validation gate's
    outlier catalogue and for UI drill-downs.
    """

    entity_id: str
    season: int
    week: int
    unit: ScoringUnit
    points: float
    breakdown: Mapping[str, float]

    @property
    def key(self) -> PlayerWeekKey:
        return (self.entity_id, self.season, self.week)
