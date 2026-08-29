from __future__ import annotations

from dataclasses import dataclass, replace

from .bye_crunch import ByeCrunchMap, bye_crunch_map
from .expected_wins import ExpectedWins, expected_wins
from .inputs import LeagueState
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams
from .playoff_odds import PlayoffOddsResult, playoff_odds
from .signal import ContendRebuildHold, contend_rebuild_hold
from .team_strength import TeamStrength, team_strength

# The Team Outlook layer (issue #12): one pure function over an assembled weekly
# league state, producing team strength, expected wins, the contend/rebuild/hold
# signal, and the bye-week crunch map — each stating the numbers behind it, none
# recommending a transaction (methodology §4).

__all__ = ["TeamOutlook", "team_outlook"]


@dataclass(frozen=True)
class TeamOutlook:
    """Everything the Team Outlook layer reports for one weekly snapshot."""

    season: int
    week: int
    team_strength: TeamStrength
    expected_wins: ExpectedWins
    playoff_odds: PlayoffOddsResult
    signal: ContendRebuildHold
    bye_crunch: ByeCrunchMap


def team_outlook(
    state: LeagueState,
    *,
    params: StrategyParams = DEFAULT_STRATEGY_PARAMS,
    playoff_sim_seed: int | None = None,
) -> TeamOutlook:
    """Assemble the Team Outlook for ``state``.

    ``playoff_sim_seed`` overrides ``params.playoff_sim_seed`` for the
    season-rest simulation — pass ``seed_from_snapshot_id(snapshot_id)`` so a
    snapshot's playoff odds (and therefore its signal) are stable across
    reloads, the same way the head-to-head sim is seeded (ADR-0007).
    """
    if playoff_sim_seed is not None:
        params = replace(params, playoff_sim_seed=playoff_sim_seed)

    strength = team_strength(state, params)
    ew = expected_wins(state, params)
    odds = playoff_odds(state, params)
    signal = contend_rebuild_hold(
        strength, odds, week=state.current_week, params=params
    )
    byes = bye_crunch_map(state, params)

    return TeamOutlook(
        season=state.season,
        week=state.current_week,
        team_strength=strength,
        expected_wins=ew,
        playoff_odds=odds,
        signal=signal,
        bye_crunch=byes,
    )
