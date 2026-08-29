from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .params import DEFAULT_STRATEGY_PARAMS, StrategyParams
from .playoff_odds import PlayoffOddsResult
from .team_strength import TeamStrength

# The contend / rebuild / hold signal (methodology §4.3): a weekly advisory from
# ~Week 5 onward, from two inputs — the team-strength percentile (§4.1) and
# season-rest playoff odds (§4.3). It states the signal and the numbers behind
# it; it recommends **no specific action** (CONTEXT.md "Contend / Rebuild / Hold
# signal"). ``recommends_transaction`` is a frozen ``False`` invariant.

__all__ = ["ContendRebuildHold", "StrategicSignal", "contend_rebuild_hold"]

StrategicSignal = Literal["contend", "rebuild", "hold", "too-early"]


@dataclass(frozen=True)
class ContendRebuildHold:
    """The signal plus every input threshold and value behind it.

    ``recommends_transaction`` is always ``False`` — the layer is advisory only
    (methodology §4: "None of them recommends a transaction"). ``rationale``
    spells out which condition fired in plain language for the UI.
    """

    signal: StrategicSignal
    week: int
    signal_start_week: int
    points_for_percentile: float
    playoff_odds: float
    contend_percentile_threshold: float
    rebuild_percentile_threshold: float
    striking_distance_playoff_odds: float
    low_playoff_odds: float
    rationale: tuple[str, ...]
    recommends_transaction: bool = False

    def __post_init__(self) -> None:
        if self.recommends_transaction:
            raise ValueError(
                "the contend/rebuild/hold signal never recommends a transaction"
            )


def contend_rebuild_hold(
    strength: TeamStrength,
    odds: PlayoffOddsResult,
    *,
    week: int,
    params: StrategyParams = DEFAULT_STRATEGY_PARAMS,
) -> ContendRebuildHold:
    """Derive the signal for ``week`` from ``strength`` and ``odds``.

    Before ``params.contend_signal_start_week`` the signal is ``"too-early"``
    (methodology §4.3, "earlier data is too thin") and the inputs are still
    reported. From that week on:

    * **contend** — points-for percentile ``>=`` the contend threshold **and**
      playoff odds ``>=`` the striking-distance floor;
    * **rebuild** — percentile ``<=`` the rebuild threshold **and** playoff
      odds ``<=`` the low floor;
    * **hold** — anything else.
    """
    pct = strength.percentile
    dp_odds = odds.dead_parrots_odds

    common = dict(
        week=week,
        signal_start_week=params.contend_signal_start_week,
        points_for_percentile=pct,
        playoff_odds=dp_odds,
        contend_percentile_threshold=params.contend_points_for_percentile,
        rebuild_percentile_threshold=params.rebuild_points_for_percentile,
        striking_distance_playoff_odds=params.striking_distance_playoff_odds,
        low_playoff_odds=params.low_playoff_odds,
    )

    if week < params.contend_signal_start_week:
        return ContendRebuildHold(
            signal="too-early",
            rationale=(
                f"Week {week} is before week {params.contend_signal_start_week}; "
                "too little data for a contend/rebuild read. Inputs shown for "
                "context only.",
            ),
            **common,
        )

    contend_pct = pct >= params.contend_points_for_percentile
    contend_odds = dp_odds >= params.striking_distance_playoff_odds
    rebuild_pct = pct <= params.rebuild_points_for_percentile
    rebuild_odds = dp_odds <= params.low_playoff_odds

    if contend_pct and contend_odds:
        signal: StrategicSignal = "contend"
        rationale = (
            f"Points-for percentile {pct:.0f} is at or above the contend "
            f"threshold ({params.contend_points_for_percentile:.0f}).",
            f"Season-rest playoff odds {dp_odds:.0%} are at or above the "
            f"striking-distance floor ({params.striking_distance_playoff_odds:.0%}).",
            "Advisory only — no transaction is recommended.",
        )
    elif rebuild_pct and rebuild_odds:
        signal = "rebuild"
        rationale = (
            f"Points-for percentile {pct:.0f} is at or below the rebuild "
            f"threshold ({params.rebuild_points_for_percentile:.0f}).",
            f"Season-rest playoff odds {dp_odds:.0%} are at or below the low "
            f"floor ({params.low_playoff_odds:.0%}).",
            "Advisory only — no transaction is recommended.",
        )
    else:
        signal = "hold"
        bits: list[str] = []
        if contend_pct and not contend_odds:
            bits.append(
                f"Points-for percentile {pct:.0f} clears the contend threshold "
                f"but playoff odds {dp_odds:.0%} fall short of the "
                f"striking-distance floor ({params.striking_distance_playoff_odds:.0%})."
            )
        elif rebuild_pct and not rebuild_odds:
            bits.append(
                f"Points-for percentile {pct:.0f} is in rebuild range but "
                f"playoff odds {dp_odds:.0%} are above the low floor "
                f"({params.low_playoff_odds:.0%})."
            )
        else:
            bits.append(
                f"Points-for percentile {pct:.0f} sits between the rebuild "
                f"({params.rebuild_points_for_percentile:.0f}) and contend "
                f"({params.contend_points_for_percentile:.0f}) thresholds."
            )
        bits.append("Advisory only — no transaction is recommended.")
        rationale = tuple(bits)

    return ContendRebuildHold(signal=signal, rationale=rationale, **common)
