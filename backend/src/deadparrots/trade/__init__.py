"""RIP TIDE Trade Desk layer (issue #13; methodology §4.5–§4.9).

``trade_desk(state)`` is a pure function over an assembled weekly
:class:`TradeDeskState`, producing four reads and nothing that recommends a
transaction:

* :func:`opportunity_score` — a per-player index from nflverse usage (snap,
  target, route, red-zone shares, equal-weighted, decay-weighted) set beside
  the player's fantasy-points trend;
* :func:`trade_candidates` — buy-low (opportunity up, output lagging) and
  sell-high (output spiking, opportunity flat/declining) targets, sell-high
  weighted up for injury risk or a hard schedule, each surfaced only when the
  **trade edge** — the positional-rank gap between the external consensus
  market-value proxy and the model's opportunity-adjusted rank — clears roughly
  one positional tier;
* :func:`desperate_team_read` — the other 11 managers ranked by a composite of
  sub-.500 record, low points-for percentile, roster age (nflverse birthdates)
  and their own bye crunch, with the top 2–3 surfaced with reasons;
* :func:`trade_deadline_countdown` — days to the November 28 trade deadline.

Every tunable is in :class:`TradeParams`, transcribed from the signed-off
``docs/methodology.md`` and its §6 review answers. See ADR-0010.
"""

from __future__ import annotations

from .candidates import TradeCandidate, TradeSide, trade_candidates
from .countdown import TradeDeadlineCountdown, trade_deadline_countdown
from .desk import TradeDesk, trade_desk
from .desperate import (
    DesperateComponent,
    DesperateTeam,
    DesperateTeamRead,
    desperate_team_read,
)
from .inputs import (
    PlayerWeek,
    RivalRosterSpot,
    RivalTeam,
    TradeDeskState,
    TradePlayer,
    UsageSnapshot,
)
from .opportunity import OpportunityScore, opportunity_score
from .params import DEFAULT_TRADE_PARAMS, TradeParams

__all__ = [
    "DEFAULT_TRADE_PARAMS",
    "DesperateComponent",
    "DesperateTeam",
    "DesperateTeamRead",
    "OpportunityScore",
    "PlayerWeek",
    "RivalRosterSpot",
    "RivalTeam",
    "TradeCandidate",
    "TradeDeadlineCountdown",
    "TradeDesk",
    "TradeDeskState",
    "TradeParams",
    "TradePlayer",
    "TradeSide",
    "UsageSnapshot",
    "desperate_team_read",
    "opportunity_score",
    "trade_candidates",
    "trade_deadline_countdown",
    "trade_desk",
]
