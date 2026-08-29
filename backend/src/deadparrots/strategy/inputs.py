from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..lineup import RIP_TIDE_SLOTS, LineupSlots

# The Team Outlook layer's input vocabulary (issue #12; methodology §4.1–§4.4).
#
# Every strategic-layer function is pure over an *assembled weekly league
# state*: the 12 RIP TIDE teams with their scored weekly points and records, the
# remaining schedule, the Dead Parrots roster for the bye-week map, and a
# per-team weekly points forecast for the season-rest simulation. Whoever runs
# the assisted pull and the projection model is responsible for turning raw
# pulls into these frozen objects — nothing here does I/O or touches nflverse
# column names, exactly as the projection model consumes ``PlayerHistory`` /
# ``OpportunityMetrics`` rather than raw data (methodology §2).
#
# The season-rest simulation (playoff odds) takes team-level marginals
# (:class:`TeamScoringForecast`) the same way the head-to-head Monte Carlo takes
# player-level marginals (``SimPlayer``): the projection model produces the
# shape upstream, the strategy layer only plays the schedule out. See ADR-0009.

__all__ = [
    "ByePlayer",
    "LeagueState",
    "LeagueTeam",
    "RemainingMatchup",
    "TeamScoringForecast",
    "TeamWeekScore",
]


@dataclass(frozen=True)
class TeamWeekScore:
    """One team's RIP TIDE fantasy total for one *completed* week.

    ``points_for`` is what the validated scoring engine assigned that team's
    starting lineup that week — the series team strength and expected wins are
    computed from (methodology §4.1, §4.2).
    """

    week: int
    points_for: float


@dataclass(frozen=True)
class LeagueTeam:
    """One of the 12 RIP TIDE teams and its season to date.

    ``weekly_scores`` holds every completed week in any order (the layers sort
    by week). ``wins`` / ``losses`` / ``ties`` are the head-to-head record from
    the standings pull — used only to compare *actual* wins against expected
    wins (§4.2); team strength deliberately never looks at them (§4.1).
    """

    team_id: str
    team_name: str
    is_dead_parrots: bool
    wins: int
    losses: int
    ties: int
    weekly_scores: tuple[TeamWeekScore, ...]
    division: str | None = None

    @property
    def actual_wins(self) -> float:
        """Record wins with a tie counting a half, so it lines up with the
        expected-wins scale (a tie beats half a random opponent)."""
        return self.wins + 0.5 * self.ties

    @property
    def points_for_by_week(self) -> dict[int, float]:
        """``week -> points_for`` for every completed week."""
        return {s.week: s.points_for for s in self.weekly_scores}

    def points_for_series(self) -> list[float]:
        """Completed-week points-for, oldest week first — the decay helpers
        expect oldest → newest."""
        return [s.points_for for s in sorted(self.weekly_scores, key=lambda s: s.week)]


@dataclass(frozen=True)
class RemainingMatchup:
    """One not-yet-played regular-season head-to-head. Order of the two team
    ids carries no meaning (there is no home advantage in fantasy)."""

    week: int
    team_id_a: str
    team_id_b: str

    def teams(self) -> tuple[str, str]:
        return (self.team_id_a, self.team_id_b)


@dataclass(frozen=True)
class TeamScoringForecast:
    """A team's weekly RIP TIDE points distribution for the season-rest sim.

    ``mean`` / ``sigma`` / ``skew`` describe the same Cornish-Fisher shape the
    projection model reports and the head-to-head sim samples (ADR-0006) — here
    aggregated to the team's *likely starting lineup* by whoever assembled the
    state. The season-rest simulation draws each remaining week's team total
    from this and nothing else (methodology §4.3; ADR-0009).
    """

    team_id: str
    mean: float
    sigma: float
    skew: float = 0.0

    def __post_init__(self) -> None:
        if self.sigma < 0.0:
            raise ValueError(f"sigma must be non-negative: {self.sigma!r}")


@dataclass(frozen=True)
class ByePlayer:
    """One Dead Parrots rostered player, for the bye-week crunch map (§4.4).

    ``position`` is the raw Yahoo/nflverse string; ``deadparrots.lineup.role_of``
    maps it to a canonical role. ``bye_week`` is the player's NFL bye
    (``None`` once it has passed or is unknown). ``is_starter`` marks a normal
    starter at the position — only starters on bye are *counted* toward the
    warn/critical thresholds, but the whole roster (minus bye, minus
    unavailable) is what the "can a legal lineup be fielded" check draws from.
    ``available`` is ``False`` for a player ruled out for the rest of the map's
    horizon (season-ending injury); a week-to-week injury is left ``True``.
    """

    player_id: str
    name: str
    position: str
    bye_week: int | None
    is_starter: bool = True
    available: bool = True


@dataclass(frozen=True)
class LeagueState:
    """Assembled weekly league state — the single argument to ``team_outlook``.

    ``current_week`` is the upcoming (not-yet-played) week; completed weeks are
    everything in the teams' ``weekly_scores``. ``playoff_team_count`` and
    ``regular_season_weeks`` are the RIP TIDE structure (6 of 12; 14 weeks).
    ``scoring_forecasts`` must cover every team that appears in
    ``remaining_schedule``.
    """

    season: int
    current_week: int
    teams: tuple[LeagueTeam, ...]
    remaining_schedule: tuple[RemainingMatchup, ...]
    dead_parrots_roster: tuple[ByePlayer, ...]
    scoring_forecasts: tuple[TeamScoringForecast, ...]
    playoff_team_count: int = 6
    regular_season_weeks: int = 14
    lineup_slots: LineupSlots = RIP_TIDE_SLOTS

    def __post_init__(self) -> None:
        dp = [t for t in self.teams if t.is_dead_parrots]
        if len(dp) != 1:
            raise ValueError(
                f"exactly one team must be flagged is_dead_parrots (got {len(dp)})"
            )
        ids = [t.team_id for t in self.teams]
        if len(set(ids)) != len(ids):
            raise ValueError("team_id values must be unique")

    @property
    def dead_parrots(self) -> LeagueTeam:
        return next(t for t in self.teams if t.is_dead_parrots)

    @property
    def other_teams(self) -> tuple[LeagueTeam, ...]:
        return tuple(t for t in self.teams if not t.is_dead_parrots)

    def team(self, team_id: str) -> LeagueTeam:
        try:
            return next(t for t in self.teams if t.team_id == team_id)
        except StopIteration:
            raise KeyError(f"no team with id {team_id!r}") from None

    def forecasts_by_team(self) -> Mapping[str, TeamScoringForecast]:
        return {f.team_id: f for f in self.scoring_forecasts}

    def completed_weeks(self) -> tuple[int, ...]:
        """Every week for which at least one team has a recorded score,
        ascending."""
        weeks = {s.week for t in self.teams for s in t.weekly_scores}
        return tuple(sorted(weeks))
