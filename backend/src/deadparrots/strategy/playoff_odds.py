from __future__ import annotations

import random
from dataclasses import dataclass

from ..projection import cornish_fisher_unit
from .inputs import LeagueState, TeamScoringForecast
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams

# Playoff odds via a season-rest simulation (methodology §4.3): play the
# remaining schedule out, trial after trial, drawing each team's weekly total
# from its :class:`TeamScoringForecast` marginal (the projection model's shape,
# aggregated upstream to the team's likely lineup — ADR-0009). A team makes the
# playoffs in a trial if it finishes in the top ``playoff_team_count`` by
# (final wins, then total points-for) once every remaining week is played.
#
# The draw is a single seeded RNG walked in a fixed order (week, then matchup,
# then the two teams), so identical state and seed give identical odds. Opposing
# teams in one matchup are drawn independently — game-script correlation between
# the two sides is a documented simplification here, as the methodology keeps
# the joint model in the head-to-head sim (§3.9).

__all__ = ["PlayoffOddsResult", "TeamPlayoffOdds", "playoff_odds"]


@dataclass(frozen=True)
class TeamPlayoffOdds:
    """One team's season-rest outcome distribution."""

    team_id: str
    team_name: str
    is_dead_parrots: bool
    playoff_odds: float
    mean_final_wins: float
    current_wins: float
    remaining_games: int


@dataclass(frozen=True)
class PlayoffOddsResult:
    """The season-rest sim's answer for the whole league."""

    trials: int
    rng_seed: int
    playoff_team_count: int
    by_team: tuple[TeamPlayoffOdds, ...]

    def odds_for(self, team_id: str) -> float:
        try:
            return next(t.playoff_odds for t in self.by_team if t.team_id == team_id)
        except StopIteration:
            raise KeyError(f"no team with id {team_id!r}") from None

    @property
    def dead_parrots_odds(self) -> float:
        return next(t.playoff_odds for t in self.by_team if t.is_dead_parrots)


def _draw(rng: random.Random, forecast: TeamScoringForecast) -> float:
    """One weekly total from a team's marginal — the same Cornish-Fisher shape
    the projection model and the head-to-head sim use (ADR-0006)."""
    z = rng.gauss(0.0, 1.0)
    return forecast.mean + cornish_fisher_unit(z, forecast.skew) * forecast.sigma


def playoff_odds(
    state: LeagueState, params: StrategyParams = DEFAULT_STRATEGY_PARAMS
) -> PlayoffOddsResult:
    """Run the season-rest simulation over ``state`` (methodology §4.3).

    ``params.playoff_sim_seed`` seeds it; pass a per-snapshot seed via
    ``team_outlook(..., playoff_sim_seed=...)`` in practice so a snapshot's
    odds are reproducible. Every team in ``remaining_schedule`` must have a
    :class:`TeamScoringForecast`.
    """
    forecasts = state.forecasts_by_team()
    missing = {
        tid
        for m in state.remaining_schedule
        for tid in m.teams()
        if tid not in forecasts
    }
    if missing:
        raise ValueError(
            f"no TeamScoringForecast for team(s) {sorted(missing)} in the "
            "remaining schedule"
        )

    team_ids = [t.team_id for t in state.teams]
    current_wins = {t.team_id: t.actual_wins for t in state.teams}
    current_points = {
        t.team_id: sum(s.points_for for s in t.weekly_scores) for t in state.teams
    }
    remaining_games = {tid: 0 for tid in team_ids}
    for m in state.remaining_schedule:
        for tid in m.teams():
            if tid in remaining_games:
                remaining_games[tid] += 1

    schedule = sorted(
        state.remaining_schedule, key=lambda m: (m.week, m.team_id_a, m.team_id_b)
    )
    cutoff = state.playoff_team_count
    trials = params.playoff_sim_trials
    rng = random.Random(params.playoff_sim_seed)

    made_playoffs = {tid: 0 for tid in team_ids}
    wins_accumulator = {tid: 0.0 for tid in team_ids}

    for _ in range(trials):
        wins = dict(current_wins)
        points = dict(current_points)
        for m in schedule:
            a, b = m.team_id_a, m.team_id_b
            score_a = _draw(rng, forecasts[a])
            score_b = _draw(rng, forecasts[b])
            points[a] += score_a
            points[b] += score_b
            if score_a > score_b:
                wins[a] += 1.0
            elif score_b > score_a:
                wins[b] += 1.0
            else:
                wins[a] += 0.5
                wins[b] += 0.5

        for tid in team_ids:
            wins_accumulator[tid] += wins[tid]

        standings = sorted(
            team_ids, key=lambda tid: (-wins[tid], -points[tid], tid)
        )
        for tid in standings[:cutoff]:
            made_playoffs[tid] += 1

    by_team = tuple(
        TeamPlayoffOdds(
            team_id=t.team_id,
            team_name=t.team_name,
            is_dead_parrots=t.is_dead_parrots,
            playoff_odds=round(made_playoffs[t.team_id] / trials, 4),
            mean_final_wins=round(wins_accumulator[t.team_id] / trials, 4),
            current_wins=current_wins[t.team_id],
            remaining_games=remaining_games[t.team_id],
        )
        for t in state.teams
    )

    return PlayoffOddsResult(
        trials=trials,
        rng_seed=params.playoff_sim_seed,
        playoff_team_count=cutoff,
        by_team=by_team,
    )
