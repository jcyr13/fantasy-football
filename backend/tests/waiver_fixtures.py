"""Shared builders for the Waiver / Free Agents layer tests (issue #14)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from deadparrots.waiver import FreeAgent, RosteredPlayer, WaiverState

SEASON = 2026
WEEK = 8
AS_OF = date(2026, 10, 20)


def fa(
    player_id: str,
    position: str,
    *,
    ros: float,
    ceiling: float | None = None,
    bye_week: int | None = None,
    name: str | None = None,
) -> FreeAgent:
    """A :class:`FreeAgent`. ``ceiling`` defaults to a tenth of the
    rest-of-season total so the two sort keys usually agree unless a test sets
    them apart on purpose."""
    return FreeAgent(
        player_id=player_id,
        name=name or player_id.replace("-", " ").title(),
        position=position,
        ros_projected_points=ros,
        next_week_ceiling=ceiling if ceiling is not None else round(ros / 10.0, 2),
        bye_week=bye_week,
    )


def rostered(
    player_id: str,
    position: str,
    *,
    bye_week: int | None = None,
    is_starter: bool = True,
    available: bool = True,
    out_this_week: bool = False,
    name: str | None = None,
) -> RosteredPlayer:
    return RosteredPlayer(
        player_id=player_id,
        name=name or player_id,
        position=position,
        bye_week=bye_week,
        is_starter=is_starter,
        available=available,
        out_this_week=out_this_week,
    )


def full_roster(
    *,
    qb: int = 2,
    rb: int = 4,
    wr: int = 4,
    te: int = 2,
    k: int = 1,
    def_: int = 1,
    idp: int = 1,
    byes: dict[str, int] | None = None,
    bench: set[str] | None = None,
    unavailable: set[str] | None = None,
    out_this_week: set[str] | None = None,
) -> tuple[RosteredPlayer, ...]:
    """A Dead Parrots roster with the given per-position counts, deep enough at
    every position to cover the fixed slots. ``byes`` maps a ``player_id``
    (``"rb1"``, ``"k1"``, …) to an NFL bye week; ``bench`` marks ids as
    non-starters; ``unavailable`` marks ids ruled out for the season;
    ``out_this_week`` marks ids as a week-to-week injury out for the upcoming
    week only."""
    byes = byes or {}
    bench = bench or set()
    unavailable = unavailable or set()
    out_this_week = out_this_week or set()
    out: list[RosteredPlayer] = []
    for position, count in (
        ("QB", qb),
        ("RB", rb),
        ("WR", wr),
        ("TE", te),
        ("K", k),
        ("DEF", def_),
        ("IDP", idp),
    ):
        for i in range(count):
            pid = f"{position.lower()}{i + 1}"
            out.append(
                rostered(
                    pid,
                    position,
                    bye_week=byes.get(pid),
                    is_starter=pid not in bench,
                    available=pid not in unavailable,
                    out_this_week=pid in out_this_week,
                )
            )
    return tuple(out)


def a_state(
    *,
    free_agents: Sequence[FreeAgent] = (),
    roster: Sequence[RosteredPlayer] | None = None,
    season: int = SEASON,
    current_week: int = WEEK,
    as_of_date: date = AS_OF,
    waiver_priority: int = 4,
    team_count: int = 12,
    regular_season_weeks: int = 14,
    hole_roles: frozenset[str] | None = None,
) -> WaiverState:
    return WaiverState(
        season=season,
        current_week=current_week,
        as_of_date=as_of_date,
        free_agents=tuple(free_agents),
        dead_parrots_roster=tuple(roster) if roster is not None else full_roster(),
        waiver_priority=waiver_priority,
        team_count=team_count,
        regular_season_weeks=regular_season_weeks,
        hole_roles=hole_roles,
    )
