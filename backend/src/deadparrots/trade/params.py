from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# Every tunable in the Trade Desk layer, in one frozen table (methodology §4.5–
# §4.9 and §5 rows 11–12). The methodology-pinned values are transcribed from
# the signed-off ``docs/methodology.md`` and its §6 review answers ("accepted as
# documented"); ``test_trade_params.py`` pins them so a drift from the doc fails
# CI, exactly as ``ProjectionParams`` / ``StrategyParams`` do for their layers.
#
# The trend slopes (§4.6) are the one place §5 puts no number on the knob — §4.6
# only says "trending up" / "flat or declining" / "spiking" / "lags". Their
# defaults are chosen to match that prose on the natural scale of each series
# (usage shares in [0, 1]; fantasy points in the tens) and are surfaced here so
# they can be tuned without a code change. See ADR-0010.

# §6 Q4, accepted as documented: give "one positional tier" a number — edge ≥ 12
# ranks at RB/WR, ≥ 6 at QB/TE. The shallow-bench roster positions (K/DEF/IDP)
# take the same 6 as QB/TE; they are rarely trade chips but RIP TIDE rosters
# them, and a 6-rank gap is a full tier there too. The map covers every role
# ``role_of`` can return; ``_FALLBACK_EDGE_TIER`` only guards an unexpected
# spelling and is never hit in practice.
_EDGE_TIER_BY_ROLE: Mapping[str, int] = MappingProxyType(
    {"RB": 12, "WR": 12, "QB": 6, "TE": 6, "K": 6, "DEF": 6, "IDP": 6}
)
_FALLBACK_EDGE_TIER = 6


@dataclass(frozen=True)
class TradeParams:
    """Defaults for the opportunity score, buy-low / sell-high classification,
    the trade-edge surfacing threshold, and the desperate-team read."""

    # --- opportunity score (methodology §4.5) --------------------------
    # Decay half-life for every trailing usage / output statistic, in games.
    # Matches the projection model's 4-game player-history half-life (§5 row 1)
    # so "recent form" means the same thing everywhere.
    opportunity_decay_half_life_games: float = 4.0
    # The four usage signals are equal-weighted into the composite index
    # (methodology §4.5 / §6 Q6 accepts equal weights).
    usage_weight_snap_share: float = 0.25
    usage_weight_target_share: float = 0.25
    usage_weight_route_participation: float = 0.25
    usage_weight_red_zone_share: float = 0.25

    # --- buy-low / sell-high trend thresholds (methodology §4.6) -------
    # Decay-weighted per-game slope of the usage composite (a share, so slopes
    # are small): at or above ``up`` counts as "trending up"; at or below
    # ``flat`` (negatives included) counts as "flat or declining".
    opportunity_up_slope: float = 0.01
    opportunity_flat_slope: float = 0.005
    # Decay-weighted per-game slope of fantasy points: at or above ``spike``
    # counts as "output spiking"; at or below ``lag`` counts as output that
    # "lags" a rising usage trend.
    output_spike_slope: float = 1.5
    output_lag_slope: float = 0.5

    # --- trade edge surfacing threshold (methodology §4.8 / §6 Q4) ----
    # Minimum positional-rank gap between the market-value proxy and the model's
    # opportunity-adjusted rank for a candidate to be surfaced ("roughly one
    # positional tier"). Per role, keyed by the canonical role string.
    edge_tier_by_role: Mapping[str, int] = field(default_factory=lambda: _EDGE_TIER_BY_ROLE)

    # --- sell-high weighting (methodology §4.6) -----------------------
    # Sell-high is weighted up for injury risk or a hard upcoming schedule,
    # "because the market is slowest to price those in" — so the weight scales
    # the edge for *both* the surfacing test and the ranking, letting a
    # borderline sub-tier edge clear the threshold when the risk is real.
    # The multiplier is ``1 + injury_bonus * injury_risk + schedule_bonus *
    # hardness``.
    sell_high_injury_bonus: float = 0.5
    sell_high_hard_schedule_bonus: float = 0.5
    # "Hard" schedule: the upcoming opponent allows this fraction (or less) of
    # the league-average fantasy points to the player's position. Linear
    # ramp — hardness 0 at parity, 1 at or below this ratio.
    hard_schedule_ratio: float = 0.9

    # --- desperate-team read (methodology §4.9 / §6 Q5) --------------
    # Four equally-weighted components: sub-.500 record, low points-for
    # percentile, mean roster age, own bye-week crunch.
    desperate_weight_record: float = 0.25
    desperate_weight_points_for: float = 0.25
    desperate_weight_roster_age: float = 0.25
    desperate_weight_bye_crunch: float = 0.25
    # Team-strength decay half-life for the points-for percentile component,
    # in weeks (methodology §4.1; matches the Team Outlook layer).
    team_strength_decay_half_life_weeks: float = 4.0
    # Surface the top N most-desperate rivals ("top 2–3").
    desperate_surface_count: int = 3
    # A component with this normalized strength or more is called out by name in
    # a surfaced team's reasons.
    desperate_reason_threshold: float = 0.5

    # --- November 28 countdown -------------------------------------
    trade_deadline_month: int = 11
    trade_deadline_day: int = 28

    def __post_init__(self) -> None:
        usage = [
            self.usage_weight_snap_share,
            self.usage_weight_target_share,
            self.usage_weight_route_participation,
            self.usage_weight_red_zone_share,
        ]
        if abs(sum(usage) - 1.0) > 1e-9:
            raise ValueError(f"usage weights must sum to 1.0: {usage}")
        desperate = [
            self.desperate_weight_record,
            self.desperate_weight_points_for,
            self.desperate_weight_roster_age,
            self.desperate_weight_bye_crunch,
        ]
        if abs(sum(desperate) - 1.0) > 1e-9:
            raise ValueError(f"desperate-team weights must sum to 1.0: {desperate}")
        if self.opportunity_flat_slope > self.opportunity_up_slope:
            raise ValueError("opportunity_flat_slope must not exceed opportunity_up_slope")
        if self.output_lag_slope > self.output_spike_slope:
            raise ValueError("output_lag_slope must not exceed output_spike_slope")
        if not 0.0 < self.hard_schedule_ratio <= 1.0:
            raise ValueError("hard_schedule_ratio must be in (0, 1]")
        if self.desperate_surface_count < 1:
            raise ValueError("desperate_surface_count must be >= 1")

    def usage_weights(self) -> dict[str, float]:
        """The four usage-signal weights keyed by :class:`UsageSnapshot` field."""
        return {
            "snap_share": self.usage_weight_snap_share,
            "target_share": self.usage_weight_target_share,
            "route_participation": self.usage_weight_route_participation,
            "red_zone_share": self.usage_weight_red_zone_share,
        }

    def edge_tier_for(self, role: str) -> int:
        """The one-positional-tier edge threshold for ``role`` (§4.8 / §6 Q4)."""
        return self.edge_tier_by_role.get(role, _FALLBACK_EDGE_TIER)


DEFAULT_TRADE_PARAMS = TradeParams()
"""The signed-off methodology defaults — what ``trade_desk`` uses unless
overridden."""
