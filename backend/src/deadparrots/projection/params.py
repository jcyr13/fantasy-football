from __future__ import annotations

from dataclasses import dataclass

# Every tunable in the projection model, in one frozen table (methodology §5).
# The values here are transcribed from the signed-off ``docs/methodology.md``;
# a reviewer should be able to read this file against §3 and §5 of that document
# and find every default accounted for. ``test_projection_params.py`` pins the
# methodology-derived numbers so a drift from the doc fails CI.


@dataclass(frozen=True)
class ProjectionParams:
    """Defaults for the weekly point-distribution model.

    The three "not in §5" knobs (``opportunity_trend_sensitivity``, the usage
    weights, ``residual_volume_floor``, and the Monte-Carlo settings) are
    implementation constants §3 describes qualitatively but does not put a
    number on; they are surfaced here so they can be tuned without a code
    change. Their defaults are chosen to match §3's prose, not invented signal.
    """

    # --- methodology §5, row 1 / §3.3 ------------------------------------
    # Player-history decay half-life, in games. The single most impactful
    # parameter and the first to revisit (backtest 2–6 game half-lives).
    decay_half_life_games: float = 4.0

    # --- methodology §5, row 2 / §3.5 ----------------------------------
    # The matchup factor is clamped to ``[1 - cap, 1 + cap]`` — at most ±20%.
    matchup_adjustment_cap: float = 0.20

    # --- methodology §5, row 3 / §3.6 ----------------------------------
    # A player needs this many games in the current season before their own
    # residual shape fully overrides the positional prior.
    own_shape_min_games: int = 4

    # --- methodology §5, row 5 / §3.8 ----------------------------------
    # Weeks ``<=`` this are labelled low-confidence / prior-driven regardless of
    # the per-player history rule (no current-season data exists yet).
    early_season_week_max: int = 3

    # --- §3.4, opportunity trend adjustment (no §5 row) ----------------
    # The mean is scaled by ``1 + sensitivity * combined_slope`` where
    # ``combined_slope`` is the weighted sum of the four usage signals'
    # decay-weighted per-game slopes. §3.4 says this adjustment is *not*
    # separately capped — it is bounded in practice by the [0, 1] range of the
    # underlying shares. ``sensitivity = 1.0`` means "a +0.10/game combined
    # share trend lifts the mean 10%".
    opportunity_trend_sensitivity: float = 1.0
    # The four signals are equal-weighted (methodology §4.5 / open question 6
    # accepts equal weights for the usage composite).
    usage_weight_snap_share: float = 0.25
    usage_weight_target_share: float = 0.25
    usage_weight_route_participation: float = 0.25
    usage_weight_red_zone_share: float = 0.25
    # Numeric guard only: keep ``1 + sensitivity * combined_slope`` at or above
    # this so a wild negative trend cannot drive the mean to zero or below. Not
    # a cap on the signal — it only bites on implausible slopes.
    opportunity_trend_floor: float = 0.10

    # --- residual shape scaling (§3.2 step 2) -------------------------
    # The positional residual spread is a fraction of the player's projected
    # volume; this floor stops the floor/ceiling gap from collapsing on a
    # genuinely low-mean projection (a kicker projected 7 points still has a
    # real error bar).
    residual_volume_floor: float = 3.0
    # Own-residual skew is clamped to this magnitude before it feeds the
    # sampler. The Cornish-Fisher draw stays monotonic in ``z`` down to
    # ``z = -3 / clamp``; at 1.0 that is ``z = -3`` (~0.1st percentile), well
    # below the P10 the model reports, so a noisy three-game skew estimate can
    # never reorder the quantiles.
    own_skew_clamp: float = 1.0

    # --- Monte-Carlo marginal distribution ---------------------------
    # Draw count for the per-player point distribution. Fixed + seeded, so the
    # output is identical for identical inputs (spec acceptance criterion 5).
    sample_count: int = 20_000
    floor_quantile: float = 0.10
    projection_quantile: float = 0.50
    ceiling_quantile: float = 0.90
    # Strict minimum gap enforced between the three reported quantiles after
    # rounding, so ``P10 < P50 < P90`` holds even for a degenerate input.
    min_quantile_gap: float = 0.01

    def usage_weights(self) -> dict[str, float]:
        """The four usage-signal weights keyed by :class:`UsageSnapshot` field."""
        return {
            "snap_share": self.usage_weight_snap_share,
            "target_share": self.usage_weight_target_share,
            "route_participation": self.usage_weight_route_participation,
            "red_zone_share": self.usage_weight_red_zone_share,
        }


DEFAULT_PARAMS = ProjectionParams()
"""The signed-off methodology defaults — what ``project`` uses unless overridden."""
