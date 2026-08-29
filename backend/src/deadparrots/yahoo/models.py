from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# The normalized Yahoo domain objects (spec issue #7). Everything downstream of
# the source interface consumes these and never sees a raw payload — so nothing
# downstream knows or cares whether the data came from the browser scrape or,
# later, the official Yahoo API (docs/adr/0001).
#
# Vocabulary follows CONTEXT.md: "Opponent likely lineup", "Waiver priority",
# "Assisted pull".

# Yahoo's non-playing roster slots. Everything else is a starting slot.
BENCH_SLOTS: frozenset[str] = frozenset({"BN", "IR", "IR+"})


@dataclass(frozen=True)
class RosterEntry:
    """One player on a team's matchup roster, as Yahoo lists them."""

    slot: str
    player_name: str
    nfl_team: str | None
    position: str | None
    opponent: str | None
    yahoo_projected_points: float | None
    injury_status: str | None

    @property
    def is_starter(self) -> bool:
        return self.slot.upper() not in BENCH_SLOTS


@dataclass(frozen=True)
class TeamSide:
    """One side of a matchup: the team, its manager, and its full roster."""

    team_name: str
    manager: str | None
    is_dead_parrots: bool
    entries: tuple[RosterEntry, ...]

    @property
    def starters(self) -> tuple[RosterEntry, ...]:
        return tuple(e for e in self.entries if e.is_starter)

    @property
    def bench(self) -> tuple[RosterEntry, ...]:
        return tuple(e for e in self.entries if not e.is_starter)

    @property
    def yahoo_projected_total(self) -> float | None:
        """Sum of Yahoo's projections across the starters, or ``None`` if any
        starter is missing one (a partial sum would read as a real, lower total).
        """
        projections = [e.yahoo_projected_points for e in self.starters]
        if not projections or any(p is None for p in projections):
            return None
        return round(sum(p for p in projections if p is not None), 2)


@dataclass(frozen=True)
class MatchupSnapshot:
    """The current-week head-to-head: Dead Parrots vs. one opponent, both
    rosters, both Yahoo projections (CONTEXT.md "Matchup").
    """

    week: int
    dead_parrots: TeamSide
    opponent: TeamSide


@dataclass(frozen=True)
class FreeAgentEntry:
    """A waiver-eligible / free-agent player from Yahoo's players page."""

    player_name: str
    nfl_team: str | None
    position: str
    availability: Literal["FA", "W"]
    waiver_claim_date: str | None
    percent_rostered: float | None
    yahoo_projected_points: float | None
    opponent: str | None
    injury_status: str | None


@dataclass(frozen=True)
class FreeAgentListing:
    players: tuple[FreeAgentEntry, ...]


@dataclass(frozen=True)
class InjuryEntry:
    """One row of Yahoo's injury report."""

    player_name: str
    nfl_team: str | None
    position: str | None
    status: str
    detail: str | None
    updated: str | None


@dataclass(frozen=True)
class InjuryReport:
    entries: tuple[InjuryEntry, ...]


@dataclass(frozen=True)
class StandingsRow:
    """One team's standings line: record, points, division, and — when Yahoo
    exposes it — waiver priority (CONTEXT.md "Waiver priority").
    """

    rank: int | None
    team_name: str
    manager: str | None
    division: str | None
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    waiver_priority: int | None


WaiverPrioritySource = Literal["standings", "manual-entry-required"]


@dataclass(frozen=True)
class StandingsSnapshot:
    """League standings plus where waiver priority came from. When the standings
    page does not carry a waiver-priority column, ``waiver_priority_source`` is
    ``"manual-entry-required"`` and the pull has flagged it for John to enter by
    hand (spec issue #7, last acceptance criterion).
    """

    rows: tuple[StandingsRow, ...]
    waiver_priority_source: WaiverPrioritySource

    @property
    def waiver_priority_needs_manual_entry(self) -> bool:
        return self.waiver_priority_source == "manual-entry-required"
