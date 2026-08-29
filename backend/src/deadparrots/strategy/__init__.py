"""RIP TIDE Team Outlook layer (issue #12; methodology §4.1–§4.4).

``team_outlook(state)`` is a pure function over an assembled weekly
:class:`LeagueState`, producing four advisory reads and nothing that recommends
a transaction:

* :func:`team_strength` — Dead Parrots' decay-weighted rolling points-for as a
  percentile against the other 11 teams (never win/loss record);
* :func:`expected_wins` — how many weeks Dead Parrots' scores would have beaten
  a randomly drawn league opponent, against actual wins, to expose luck;
* :func:`contend_rebuild_hold` — a contend / rebuild / hold signal from ~Week 5,
  from the team-strength percentile and season-rest playoff odds, with every
  input threshold shown;
* :func:`bye_crunch_map` — per upcoming week, Dead Parrots starters on bye by
  position, graded warn (2 at a position) / critical (3+, or no legal healthy
  lineup fieldable).

Playoff odds come from :func:`playoff_odds`, a season-rest simulation that plays
the remaining schedule out over per-team weekly marginals (the projection
model's shape, aggregated upstream — ADR-0009). Every tunable is in
:class:`StrategyParams`, transcribed from the signed-off ``docs/methodology.md``.
"""

from __future__ import annotations

from .bye_crunch import (
    ByeCrunchGrade,
    ByeCrunchMap,
    PositionByeCount,
    WeekByeCrunch,
    bye_crunch_map,
)
from .expected_wins import ExpectedWins, WeeklyExpectedWins, expected_wins
from .inputs import (
    ByePlayer,
    LeagueState,
    LeagueTeam,
    RemainingMatchup,
    TeamScoringForecast,
    TeamWeekScore,
)
from .outlook import TeamOutlook, team_outlook
from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams
from .playoff_odds import PlayoffOddsResult, TeamPlayoffOdds, playoff_odds
from .signal import ContendRebuildHold, StrategicSignal, contend_rebuild_hold
from .team_strength import TeamStrength, TeamStrengthValue, team_strength

__all__ = [
    "DEFAULT_STRATEGY_PARAMS",
    "ByeCrunchGrade",
    "ByeCrunchMap",
    "ByePlayer",
    "ContendRebuildHold",
    "ExpectedWins",
    "LeagueState",
    "LeagueTeam",
    "PlayoffOddsResult",
    "PositionByeCount",
    "RemainingMatchup",
    "StrategicSignal",
    "StrategyParams",
    "TeamOutlook",
    "TeamPlayoffOdds",
    "TeamScoringForecast",
    "TeamStrength",
    "TeamStrengthValue",
    "TeamWeekScore",
    "WeekByeCrunch",
    "WeeklyExpectedWins",
    "bye_crunch_map",
    "contend_rebuild_hold",
    "expected_wins",
    "playoff_odds",
    "team_outlook",
    "team_strength",
]
