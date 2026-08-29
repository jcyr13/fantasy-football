from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .inputs import TradeDeskState
from .params import DEFAULT_TRADE_PARAMS, TradeParams

# The countdown to the November 28 trade deadline (issue #13). A plain,
# snapshot-dated difference in days: positive before the deadline, zero on the
# day, negative once it has passed.

__all__ = ["TradeDeadlineCountdown", "trade_deadline_countdown"]


@dataclass(frozen=True)
class TradeDeadlineCountdown:
    """Days from the snapshot date to the November 28 trade deadline."""

    target_date: date
    as_of: date
    days_remaining: int
    is_past: bool


def trade_deadline_countdown(
    state: TradeDeskState, params: TradeParams = DEFAULT_TRADE_PARAMS
) -> TradeDeadlineCountdown:
    """The November 28 countdown for ``state`` (deadline year = ``state.season``)."""
    target = date(state.season, params.trade_deadline_month, params.trade_deadline_day)
    days_remaining = (target - state.as_of_date).days
    return TradeDeadlineCountdown(
        target_date=target,
        as_of=state.as_of_date,
        days_remaining=days_remaining,
        is_past=days_remaining < 0,
    )
