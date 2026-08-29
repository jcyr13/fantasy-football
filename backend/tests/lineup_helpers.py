"""Shared builders for the lineup-optimizer tests (issue #11)."""

from __future__ import annotations

from deadparrots.lineup import RosterPlayer
from deadparrots.simulation import SimPlayer


def rp(
    player_id: str,
    position: str,
    *,
    mean: float,
    sigma: float = 5.0,
    skew: float = 0.3,
    name: str | None = None,
    available: bool = True,
    nfl_team: str | None = None,
    game_id: str | None = None,
) -> RosterPlayer:
    """A ``RosterPlayer`` with its marginal, terse enough for table-style specs."""
    return RosterPlayer(
        player_id=player_id,
        name=name or player_id,
        position=position,
        sim=SimPlayer(
            player_id=player_id,
            position=position,
            mean=mean,
            sigma=sigma,
            skew=skew,
            nfl_team=nfl_team,
            game_id=game_id,
        ),
        available=available,
    )


def a_roster(
    *,
    qb: int = 2,
    rb: int = 4,
    wr: int = 4,
    te: int = 2,
    k: int = 1,
    def_: int = 1,
    idp: int = 1,
    mean: float = 12.0,
) -> list[RosterPlayer]:
    """A roster with the given per-position counts; means fan out by index so no
    two players tie and argmax picks are unambiguous."""
    players: list[RosterPlayer] = []
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
            players.append(rp(pid, position, mean=mean + i + len(players) * 0.01))
    return players


def ten_starters(mean: float = 11.0, *, prefix: str = "s") -> list[RosterPlayer]:
    """Exactly one legal RIP TIDE lineup's worth of players (flex = WR).

    ``prefix`` keys the ``player_id``\\ s; use a distinct one for the opponent so
    common random numbers do not fuse the two sides into an identical draw.
    """
    return [
        rp(f"{prefix}-qb", "QB", mean=mean + 9),
        rp(f"{prefix}-rb1", "RB", mean=mean + 2),
        rp(f"{prefix}-rb2", "RB", mean=mean + 1),
        rp(f"{prefix}-wr1", "WR", mean=mean + 3),
        rp(f"{prefix}-wr2", "WR", mean=mean + 2),
        rp(f"{prefix}-wr3", "WR", mean=mean),  # the W/R/T flex
        rp(f"{prefix}-te", "TE", mean=mean - 2),
        rp(f"{prefix}-k", "K", mean=mean - 3),
        rp(f"{prefix}-def", "DEF", mean=mean - 4),
        rp(f"{prefix}-d", "IDP", mean=mean - 3),
    ]
