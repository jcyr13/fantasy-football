from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..lineup import role_of
from ..projection import UsageSnapshot

# The Trade Desk layer's input vocabulary (issue #13; methodology §4.5–§4.9).
#
# Like every strategic layer, ``trade_desk`` is a pure function over an
# *assembled weekly league state*: the trade-relevant player universe with its
# scored history and usage signals, an external market-value rank and the
# model's opportunity-adjusted rest-of-season number per player, and the other
# 11 managers with the record / points-for / roster-age / bye data the
# desperate-team read needs. Whoever runs the assisted pull, the projection
# model and the consensus feed is responsible for turning raw pulls into these
# frozen objects — nothing here does I/O, touches nflverse column names, or
# imports the consensus package, exactly as ``project`` consumes a resolved
# ``consensus_points`` number rather than the feed itself (methodology §2).
#
# This is deliberately a sibling of the Team Outlook layer's ``LeagueState``
# (issue #12), not the same object: the two layers were specced and built
# independently (issue #13 is blocked only by #7 and #9). Issue #16 — the
# assembled weekly view behind the API — is where the two input shapes are
# reconciled into one.

__all__ = [
    "PlayerWeek",
    "RivalRosterSpot",
    "RivalTeam",
    "TradeDeskState",
    "TradePlayer",
    "UsageSnapshot",
]


@dataclass(frozen=True)
class PlayerWeek:
    """One completed week for a player: the RIP TIDE points the validated
    scoring engine assigned, and the four opportunity signals for that game.

    ``usage`` is ``None`` for a game whose snap / route data never landed; such
    games still count toward the history length but are skipped by the
    opportunity composite and its trend (methodology §4.5).
    """

    week: int
    fantasy_points: float
    usage: UsageSnapshot | None = None


@dataclass(frozen=True)
class TradePlayer:
    """One player in the trade-relevant universe (the Dead Parrots roster plus
    the rival players worth pitching for).

    ``market_ros_rank`` is the external consensus **rest-of-season positional
    rank** (1 = best at the position) — the market-value proxy of methodology
    §4.7, resolved by the caller from the consensus feed. ``model_ros_points``
    is the model's opportunity-adjusted rest-of-season projected points; the
    layer ranks players within a position by it to get the model's positional
    rank, and the **trade edge** (§4.8) is the gap between the two ranks.

    ``on_dead_parrots`` splits the two candidate lists: a **buy-low** target is
    someone else's player to acquire, a **sell-high** target is a Dead Parrots
    player to trade away. ``injury_risk`` (0–1) and the upcoming
    points-allowed-to-position pair drive the sell-high weighting of §4.6.
    """

    player_id: str
    name: str
    position: str
    history: tuple[PlayerWeek, ...]
    market_ros_rank: int | None = None
    model_ros_points: float | None = None
    on_dead_parrots: bool = False
    injury_risk: float = 0.0
    upcoming_opponent_points_allowed: float | None = None
    league_average_points_allowed: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.injury_risk <= 1.0:
            raise ValueError(f"injury_risk must be in [0, 1]: {self.injury_risk!r}")
        if self.market_ros_rank is not None and self.market_ros_rank < 1:
            raise ValueError(
                f"market_ros_rank is a positional rank (>= 1): {self.market_ros_rank!r}"
            )

    @property
    def role(self) -> str:
        """The canonical position bucket — ``QB`` / ``RB`` / ``WR`` / ``TE`` /
        ``K`` / ``DEF`` / ``IDP``."""
        return role_of(self.position)

    def points_series(self) -> list[float]:
        """Completed-week fantasy points, oldest week first."""
        return [w.fantasy_points for w in sorted(self.history, key=lambda w: w.week)]


@dataclass(frozen=True)
class RivalRosterSpot:
    """One rostered player on a rival team, for the desperate-team read (§4.9).

    ``birthdate`` feeds the mean-roster-age component (``None`` for a team DEF
    or when the nflverse birthdate is missing — those spots are skipped).
    ``bye_week`` is the player's NFL bye (``None`` once it has passed or is
    unknown); byes still ahead feed the bye-crunch component.
    """

    player_id: str
    name: str
    position: str
    birthdate: date | None = None
    bye_week: int | None = None


@dataclass(frozen=True)
class RivalTeam:
    """One of the other 11 RIP TIDE managers' teams.

    ``weekly_points_for`` holds every completed week's RIP TIDE team total,
    oldest week first. ``wins`` / ``losses`` / ``ties`` are the head-to-head
    record from the standings pull.
    """

    team_id: str
    team_name: str
    wins: int
    losses: int
    ties: int
    weekly_points_for: tuple[float, ...]
    roster: tuple[RivalRosterSpot, ...]

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def games_below_500(self) -> float:
        """How far below .500 the record sits, ties neutral. Zero at or above
        .500."""
        return max(0.0, float(self.losses - self.wins))


@dataclass(frozen=True)
class TradeDeskState:
    """Assembled weekly league state — the single argument to ``trade_desk``.

    ``current_week`` is the upcoming (not-yet-played) week. ``as_of_date`` is
    the snapshot date the November-28 countdown and the roster-age calculation
    are taken against. ``dead_parrots_points_for`` is the Dead Parrots' own
    completed-week team totals — needed only so the rivals' points-for
    percentile (§4.9 component 2) is against the full 12-team league.
    """

    season: int
    current_week: int
    as_of_date: date
    players: tuple[TradePlayer, ...]
    rivals: tuple[RivalTeam, ...]
    dead_parrots_points_for: tuple[float, ...]
    regular_season_weeks: int = 14

    def __post_init__(self) -> None:
        pids = [p.player_id for p in self.players]
        if len(set(pids)) != len(pids):
            raise ValueError("player_id values must be unique")
        tids = [t.team_id for t in self.rivals]
        if len(set(tids)) != len(tids):
            raise ValueError("rival team_id values must be unique")

    def upcoming_weeks(self) -> range:
        """``current_week`` through the last regular-season week, inclusive."""
        return range(self.current_week, self.regular_season_weeks + 1)
