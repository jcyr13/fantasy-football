"""Shared builders for the Team Outlook layer tests (issue #12)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from deadparrots.strategy import (
    ByePlayer,
    LeagueState,
    LeagueTeam,
    PlayoffOddsResult,
    RemainingMatchup,
    TeamPlayoffOdds,
    TeamScoringForecast,
    TeamStrength,
    TeamWeekScore,
)

# A team with a flat weekly points-for series and no record, terse enough for
# table-style specs. ``scores`` is either a ``{week: points}`` map or a list
# taken as weeks 1..n.


def team(
    team_id: str,
    scores: Mapping[int, float] | Sequence[float],
    *,
    name: str | None = None,
    is_dp: bool = False,
    wins: int = 0,
    losses: int = 0,
    ties: int = 0,
    division: str | None = None,
) -> LeagueTeam:
    if isinstance(scores, Mapping):
        weekly = tuple(TeamWeekScore(week=w, points_for=p) for w, p in scores.items())
    else:
        weekly = tuple(
            TeamWeekScore(week=i + 1, points_for=p) for i, p in enumerate(scores)
        )
    return LeagueTeam(
        team_id=team_id,
        team_name=name or team_id,
        is_dead_parrots=is_dp,
        wins=wins,
        losses=losses,
        ties=ties,
        weekly_scores=weekly,
        division=division,
    )


def forecast(
    team_id: str, mean: float, *, sigma: float = 25.0, skew: float = 0.0
) -> TeamScoringForecast:
    return TeamScoringForecast(team_id=team_id, mean=mean, sigma=sigma, skew=skew)


def bye(
    player_id: str,
    position: str,
    bye_week: int | None,
    *,
    name: str | None = None,
    is_starter: bool = True,
    available: bool = True,
) -> ByePlayer:
    return ByePlayer(
        player_id=player_id,
        name=name or player_id,
        position=position,
        bye_week=bye_week,
        is_starter=is_starter,
        available=available,
    )


def full_roster(
    *,
    qb: int = 2,
    rb: int = 4,
    wr: int = 4,
    te: int = 2,
    k: int = 2,
    def_: int = 2,
    idp: int = 2,
    byes: Mapping[str, int] | None = None,
    bench: set[str] | None = None,
    unavailable: set[str] | None = None,
) -> tuple[ByePlayer, ...]:
    """A Dead Parrots roster with the given per-position counts. ``byes`` maps a
    ``player_id`` (``"rb1"``, ``"k3"``, …) to its NFL bye week; ``bench`` marks
    ids as non-starters; ``unavailable`` marks ids ruled out for the season."""
    byes = byes or {}
    bench = bench or set()
    unavailable = unavailable or set()
    players: list[ByePlayer] = []
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
            players.append(
                bye(
                    pid,
                    position,
                    byes.get(pid),
                    is_starter=pid not in bench,
                    available=pid not in unavailable,
                )
            )
    return tuple(players)


def round_robin(team_ids: Sequence[str], weeks: Sequence[int]) -> tuple[RemainingMatchup, ...]:
    """A fixed pairing of ``team_ids`` (assumed even count) repeated for each of
    ``weeks`` — enough remaining schedule for the season-rest sim."""
    matchups: list[RemainingMatchup] = []
    half = len(team_ids) // 2
    for w in weeks:
        for a, b in zip(team_ids[:half], team_ids[half:]):
            matchups.append(RemainingMatchup(week=w, team_id_a=a, team_id_b=b))
    return tuple(matchups)


def league(
    *,
    dp_scores: Mapping[int, float] | Sequence[float],
    other_scores: Mapping[str, Sequence[float]] | None = None,
    n_other: int = 11,
    other_flat: float = 100.0,
    current_week: int = 8,
    dp_record: tuple[int, int, int] = (0, 0, 0),
    roster: Sequence[ByePlayer] | None = None,
    remaining_weeks: Sequence[int] | None = None,
    dp_forecast_mean: float = 100.0,
    other_forecast_mean: float = 100.0,
    forecast_sigma: float = 25.0,
    regular_season_weeks: int = 14,
    playoff_team_count: int = 6,
) -> LeagueState:
    """A full 12-team league state. Dead Parrots is ``"dp"``; the other teams
    are ``"t01".."t11"`` with a flat ``other_flat`` weekly series unless
    ``other_scores`` overrides them by id."""
    other_scores = other_scores or {}
    dp_wins, dp_losses, dp_ties = dp_record

    teams: list[LeagueTeam] = [
        team("dp", dp_scores, name="Dead Parrots", is_dp=True,
             wins=dp_wins, losses=dp_losses, ties=dp_ties)
    ]
    completed = (
        sorted(dp_scores) if isinstance(dp_scores, Mapping) else
        list(range(1, len(dp_scores) + 1))
    )
    for i in range(1, n_other + 1):
        tid = f"t{i:02d}"
        scores = other_scores.get(tid, [other_flat] * len(completed))
        teams.append(team(tid, scores))

    all_ids = [t.team_id for t in teams]
    weeks = list(remaining_weeks) if remaining_weeks is not None else [
        current_week,
        current_week + 1,
    ]
    schedule = round_robin(all_ids, weeks)

    forecasts = [forecast("dp", dp_forecast_mean, sigma=forecast_sigma)]
    forecasts += [
        forecast(f"t{i:02d}", other_forecast_mean, sigma=forecast_sigma)
        for i in range(1, n_other + 1)
    ]

    return LeagueState(
        season=2026,
        current_week=current_week,
        teams=tuple(teams),
        remaining_schedule=schedule,
        dead_parrots_roster=tuple(roster) if roster is not None else full_roster(),
        scoring_forecasts=tuple(forecasts),
        playoff_team_count=playoff_team_count,
        regular_season_weeks=regular_season_weeks,
    )


def strength_stub(percentile: float, *, dwpf: float = 100.0) -> TeamStrength:
    """A :class:`TeamStrength` carrying just the percentile the signal reads."""
    return TeamStrength(
        decay_weighted_points_for=dwpf,
        percentile=percentile,
        weeks_counted=7,
        half_life_weeks=4.0,
        league=(),
    )


def odds_stub(dp_odds: float) -> PlayoffOddsResult:
    """A :class:`PlayoffOddsResult` carrying just the Dead Parrots odds the
    signal reads."""
    return PlayoffOddsResult(
        trials=10_000,
        rng_seed=0,
        playoff_team_count=6,
        by_team=(
            TeamPlayoffOdds(
                team_id="dp",
                team_name="Dead Parrots",
                is_dead_parrots=True,
                playoff_odds=dp_odds,
                mean_final_wins=7.0,
                current_wins=4.0,
                remaining_games=6,
            ),
        ),
    )
