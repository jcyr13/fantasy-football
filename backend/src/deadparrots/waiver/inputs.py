from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..lineup import RIP_TIDE_SLOTS, LineupSlots, role_of

# The Waiver / Free Agents layer's input vocabulary (issue #14; methodology
# §4.10–§4.12).
#
# ``waiver_wire`` is a pure function over an *assembled weekly league state*:
# the free-agent player universe with a resolved rest-of-season projected-points
# number and a resolved next-week ceiling (P90) per player, the Dead Parrots
# roster with NFL byes / starter flags / season availability for the bench-need
# and hole computation, and the current waiver-priority slot. Whoever runs the
# assisted pull and the projection model turns raw pulls into these frozen
# objects — nothing here does I/O, touches nflverse column names, or imports the
# projection package, exactly as ``project`` consumes a resolved
# ``consensus_points`` number rather than the feed itself (methodology §2).
#
# Like the Trade Desk's ``TradeDeskState`` and the Team Outlook layer's
# ``LeagueState``, ``WaiverState`` is a deliberate *sibling* input shape, not a
# shared type — issue #14 is blocked by #7, #9 and #12 but ships independently.
# Issue #16 (the assembled weekly view behind the API) is where the layers'
# input shapes are reconciled into one. See ADR-0011.

__all__ = [
    "FreeAgent",
    "RosteredPlayer",
    "WaiverState",
]


@dataclass(frozen=True)
class FreeAgent:
    """One freely-available player (on waivers or a free agent).

    ``ros_projected_points`` is the projection model's rest-of-season total —
    projected RIP TIDE points summed over ``current_week`` through the last
    regular-season week, resolved upstream. ``next_week_ceiling`` is the
    player's next-week P90 from the same model (methodology §3.1) — the sort key
    for the streamer list (§4.11). ``bye_week`` is the player's own NFL bye
    (``None`` once it has passed or is unknown).
    """

    player_id: str
    name: str
    position: str
    ros_projected_points: float
    next_week_ceiling: float
    bye_week: int | None = None

    def __post_init__(self) -> None:
        if self.next_week_ceiling < 0.0:
            raise ValueError(
                f"next_week_ceiling must be non-negative: {self.next_week_ceiling!r}"
            )

    @property
    def role(self) -> str:
        """The canonical position bucket — ``QB`` / ``RB`` / ``WR`` / ``TE`` /
        ``K`` / ``DEF`` / ``IDP``."""
        return role_of(self.position)


@dataclass(frozen=True)
class RosteredPlayer:
    """One Dead Parrots rostered player, for the bench-need fit and the
    this-week hole detection (methodology §4.10–§4.11, drawing on §4.4).

    ``bye_week`` is the player's NFL bye (``None`` once it has passed or is
    unknown). ``is_starter`` marks a normal starter at the position — only
    starters on bye are counted toward a role's bye-crunch weeks. ``available``
    is ``False`` for a player ruled out for the rest of the season (a
    week-to-week injury stays ``True``); an unavailable player is not counted as
    healthy depth.
    """

    player_id: str
    name: str
    position: str
    bye_week: int | None = None
    is_starter: bool = True
    available: bool = True

    @property
    def role(self) -> str:
        return role_of(self.position)


@dataclass(frozen=True)
class WaiverState:
    """Assembled weekly league state — the single argument to ``waiver_wire``.

    ``current_week`` is the upcoming (not-yet-played) week; the streamer list
    and the this-week hole detection are taken against it, and the
    rest-of-season totals on the free agents cover it through
    ``regular_season_weeks``. ``as_of_date`` is the snapshot date the
    post-cutdown waiver-window flag is measured against. ``waiver_priority`` is
    the Dead Parrots' current slot in the reverse-standings queue (1 = next in
    line, ``team_count`` = already last, no FAAB — methodology §4.12).

    ``hole_roles`` overrides the derived set of roles with a current bye/injury
    hole (issue #16 may compute it from the full assembled lineup); left
    ``None`` it is derived from the roster and the fixed slot counts.
    """

    season: int
    current_week: int
    as_of_date: date
    free_agents: tuple[FreeAgent, ...]
    dead_parrots_roster: tuple[RosteredPlayer, ...]
    waiver_priority: int
    team_count: int = 12
    regular_season_weeks: int = 14
    lineup_slots: LineupSlots = RIP_TIDE_SLOTS
    hole_roles: frozenset[str] | None = None

    def __post_init__(self) -> None:
        fa_ids = [f.player_id for f in self.free_agents]
        if len(set(fa_ids)) != len(fa_ids):
            raise ValueError("free-agent player_id values must be unique")
        roster_ids = [p.player_id for p in self.dead_parrots_roster]
        if len(set(roster_ids)) != len(roster_ids):
            raise ValueError("roster player_id values must be unique")
        if not 1 <= self.waiver_priority <= self.team_count:
            raise ValueError(
                f"waiver_priority must be in [1, {self.team_count}]: "
                f"{self.waiver_priority!r}"
            )

    def upcoming_weeks(self) -> range:
        """``current_week`` through the last regular-season week, inclusive."""
        return range(self.current_week, self.regular_season_weeks + 1)

    def fixed_slot_needs(self) -> dict[str, int]:
        """``role -> number of non-flex starting slots that must be that role``
        (QB 1, RB 2, WR 2, TE 1, K 1, DEF 1, IDP 1 under the RIP TIDE slots).
        The flex is deliberately excluded — a role is thin when its own fixed
        slots are uncovered, and the flex only ever makes that worse."""
        needs: dict[str, int] = {}
        for rule in self.lineup_slots.rules:
            if not rule.is_flex:
                (only_role,) = rule.eligible_roles
                needs[only_role] = needs.get(only_role, 0) + rule.count
        return needs

    def healthy_at_role(self, role: str, week: int) -> int:
        """Rostered players of ``role`` who are available and not on bye in
        ``week``."""
        return sum(
            1
            for p in self.dead_parrots_roster
            if p.role == role and p.available and p.bye_week != week
        )

    def hole_roles_resolved(self) -> frozenset[str]:
        """Roles with a current bye/injury hole in ``current_week`` — the
        explicit ``hole_roles`` override if given, else every role whose healthy
        rostered count this week is below its fixed slot need."""
        if self.hole_roles is not None:
            return self.hole_roles
        return frozenset(
            role
            for role, need in self.fixed_slot_needs().items()
            if self.healthy_at_role(role, self.current_week) < need
        )
