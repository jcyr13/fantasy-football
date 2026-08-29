"""Shared builders for the Trade Desk layer tests (issue #13)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from deadparrots.trade import (
    PlayerWeek,
    RivalRosterSpot,
    RivalTeam,
    TradeDeskState,
    TradePlayer,
    UsageSnapshot,
)

SEASON = 2026
WEEK = 9
AS_OF = date(2026, 10, 27)


def usage(snap: float, target: float, route: float, rz: float) -> UsageSnapshot:
    return UsageSnapshot(
        snap_share=snap, target_share=target, route_participation=route, red_zone_share=rz
    )


def ramp(start: float, step: float, n: int) -> list[float]:
    """A straight-line series ``start, start+step, …`` of length ``n``."""
    return [start + step * i for i in range(n)]


def flat(value: float, n: int) -> list[float]:
    return [value] * n


def player(
    player_id: str,
    position: str,
    *,
    points: Sequence[float],
    snap: Sequence[float] | None = None,
    target: Sequence[float] | None = None,
    route: Sequence[float] | None = None,
    red_zone: Sequence[float] | None = None,
    start_week: int = 1,
    market_rank: int | None = None,
    model_points: float | None = None,
    on_dead_parrots: bool = False,
    injury_risk: float = 0.0,
    opponent_points_allowed: float | None = None,
    league_average_points_allowed: float | None = None,
) -> TradePlayer:
    """A :class:`TradePlayer` from parallel per-week lists.

    ``snap`` / ``target`` / ``route`` / ``red_zone`` default to a flat 0.5 / 0.2
    / 0.6 / 0.15 when omitted; pass ``snap=[]`` to force a usage-less history.
    """
    n = len(points)
    if snap == [] or target == [] or route == [] or red_zone == []:
        weeks = tuple(
            PlayerWeek(week=start_week + i, fantasy_points=points[i], usage=None)
            for i in range(n)
        )
    else:
        s = list(snap) if snap is not None else flat(0.5, n)
        t = list(target) if target is not None else flat(0.2, n)
        r = list(route) if route is not None else flat(0.6, n)
        z = list(red_zone) if red_zone is not None else flat(0.15, n)
        weeks = tuple(
            PlayerWeek(
                week=start_week + i,
                fantasy_points=points[i],
                usage=usage(s[i], t[i], r[i], z[i]),
            )
            for i in range(n)
        )
    return TradePlayer(
        player_id=player_id,
        name=player_id.replace("-", " ").title(),
        position=position,
        history=weeks,
        market_ros_rank=market_rank,
        model_ros_points=model_points,
        on_dead_parrots=on_dead_parrots,
        injury_risk=injury_risk,
        upcoming_opponent_points_allowed=opponent_points_allowed,
        league_average_points_allowed=league_average_points_allowed,
    )


def spot(
    player_id: str,
    position: str,
    *,
    age_years: float | None = None,
    bye_week: int | None = None,
    as_of: date = AS_OF,
) -> RivalRosterSpot:
    birthdate = (
        date(as_of.year - int(age_years), as_of.month, max(1, as_of.day - 1))
        if age_years is not None
        else None
    )
    return RivalRosterSpot(
        player_id=player_id,
        name=player_id,
        position=position,
        birthdate=birthdate,
        bye_week=bye_week,
    )


def rival(
    team_id: str,
    *,
    wins: int,
    losses: int,
    ties: int = 0,
    points_for: Sequence[float],
    roster: Sequence[RivalRosterSpot] = (),
    name: str | None = None,
) -> RivalTeam:
    return RivalTeam(
        team_id=team_id,
        team_name=name or team_id,
        wins=wins,
        losses=losses,
        ties=ties,
        weekly_points_for=tuple(points_for),
        roster=tuple(roster),
    )


def a_state(
    *,
    players: Sequence[TradePlayer] = (),
    rivals: Sequence[RivalTeam] = (),
    season: int = SEASON,
    current_week: int = WEEK,
    as_of_date: date = AS_OF,
    dead_parrots_points_for: Sequence[float] = (110.0, 120.0, 115.0, 130.0),
    regular_season_weeks: int = 14,
) -> TradeDeskState:
    return TradeDeskState(
        season=season,
        current_week=current_week,
        as_of_date=as_of_date,
        players=tuple(players),
        rivals=tuple(rivals),
        dead_parrots_points_for=tuple(dead_parrots_points_for),
        regular_season_weeks=regular_season_weeks,
    )
