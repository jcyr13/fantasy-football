from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from ..lineup import RosterPlayer
from ..news import NewsTargets
from ..projection import PlayerProjection
from ..strategy import LeagueState
from ..trade import TradeDeskState
from ..waiver import WaiverState

# The single reconciled per-week state (ADR-0013 §1). ``assemble_week`` is the
# only place that touches nflverse column names and Yahoo normalized objects
# together; everything downstream — the optimizer, the three strategic layers,
# the API response models — reads this frozen object.

__all__ = ["AssembledWeek", "AssembledPlayer"]


@dataclass(frozen=True)
class AssembledPlayer:
    """A resolved roster/free-agent player with its projection and marginal.

    ``roster_player`` carries the ``SimPlayer`` the optimizer and head-to-head
    sim consume; ``projection`` is kept for the confidence flags and the UI
    drill-down. ``resolved`` is ``False`` when the Yahoo name did not match an
    nflverse identity (the projection then leans on the Yahoo number).
    """

    player_id: str
    name: str
    position: str
    roster_player: RosterPlayer
    projection: PlayerProjection
    resolved: bool
    yahoo_projected_points: float | None
    nfl_team: str | None


@dataclass(frozen=True)
class AssembledWeek:
    """Everything the API layer needs for one week, assembled from the pulls."""

    season: int
    week: int
    as_of_date: date
    rng_seed: int

    dead_parrots_team_name: str
    opponent_team_name: str
    opponent_assumption_hint: str

    dead_parrots: tuple[AssembledPlayer, ...]
    opponent: tuple[AssembledPlayer, ...]
    free_agents: tuple[AssembledPlayer, ...]

    opponent_yahoo_starters: tuple[str, ...]
    opponent_prior_starters: tuple[str, ...] | None

    dead_parrots_yahoo_projected_total: float | None
    opponent_yahoo_projected_total: float | None

    league_state: LeagueState
    trade_state: TradeDeskState
    waiver_state: WaiverState
    news_targets: NewsTargets

    caveats: tuple[str, ...] = field(default_factory=tuple)

    def by_id(self) -> Mapping[str, AssembledPlayer]:
        out: dict[str, AssembledPlayer] = {}
        for group in (self.dead_parrots, self.opponent, self.free_agents):
            for p in group:
                out.setdefault(p.player_id, p)
        return out

    @property
    def dead_parrots_roster_players(self) -> tuple[RosterPlayer, ...]:
        return tuple(p.roster_player for p in self.dead_parrots)

    @property
    def opponent_roster_players(self) -> tuple[RosterPlayer, ...]:
        return tuple(p.roster_player for p in self.opponent)
