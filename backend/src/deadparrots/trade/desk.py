from __future__ import annotations

from dataclasses import dataclass

from .candidates import TradeCandidate, trade_candidates
from .countdown import TradeDeadlineCountdown, trade_deadline_countdown
from .desperate import DesperateTeamRead, desperate_team_read
from .inputs import TradeDeskState
from .opportunity import OpportunityScore, opportunity_score
from .params import DEFAULT_TRADE_PARAMS, TradeParams

# The Trade Desk layer (issue #13): one pure function over an assembled weekly
# league state, producing the per-player opportunity score, the surfaced
# buy-low / sell-high candidates, the desperate-team read, and the November 28
# countdown (methodology §4.5–§4.9). It recommends no transaction — every
# candidate carries the numbers and the reasons behind it.

__all__ = ["TradeDesk", "trade_desk"]


@dataclass(frozen=True)
class TradeDesk:
    """Everything the Trade Desk layer reports for one weekly snapshot."""

    season: int
    week: int
    opportunity: tuple[OpportunityScore, ...]
    candidates: tuple[TradeCandidate, ...]
    desperate_teams: DesperateTeamRead
    countdown: TradeDeadlineCountdown

    @property
    def buy_low(self) -> tuple[TradeCandidate, ...]:
        return tuple(c for c in self.candidates if c.side == "buy-low")

    @property
    def sell_high(self) -> tuple[TradeCandidate, ...]:
        return tuple(c for c in self.candidates if c.side == "sell-high")


def trade_desk(
    state: TradeDeskState, *, params: TradeParams = DEFAULT_TRADE_PARAMS
) -> TradeDesk:
    """Assemble the Trade Desk for ``state`` (methodology §4.5–§4.9)."""
    opportunity = tuple(opportunity_score(p, params) for p in state.players)
    by_id = {o.player_id: o for o in opportunity}
    candidates = trade_candidates(state, by_id, params)
    desperate = desperate_team_read(state, params)
    countdown = trade_deadline_countdown(state, params)

    return TradeDesk(
        season=state.season,
        week=state.current_week,
        opportunity=opportunity,
        candidates=candidates,
        desperate_teams=desperate,
        countdown=countdown,
    )
