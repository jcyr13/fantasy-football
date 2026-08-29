from __future__ import annotations

from dataclasses import dataclass

# Every tunable in the Team Outlook layer, in one frozen table (methodology §5,
# rows 6–10). The values here are transcribed from the signed-off
# ``docs/methodology.md``; ``test_strategy_params.py`` pins the
# methodology-derived numbers so a drift from the doc fails CI, exactly as
# ``ProjectionParams`` does for the projection model.


@dataclass(frozen=True)
class StrategyParams:
    """Defaults for team strength, expected wins, the contend/rebuild/hold
    signal, the season-rest playoff simulation, and the bye-week crunch map.

    ``striking_distance_playoff_odds`` and ``low_playoff_odds`` are the concrete
    reading of methodology §6 open question 3 ("what does 'within striking
    distance of a playoff seed' mean concretely — within N games of the 6-seed?
    A playoff-odds floor?"): a playoff-odds floor, read off the same
    season-rest sim the methodology already names for the signal. See ADR-0009.
    """

    # --- methodology §5, row 6 / §4.1 ---------------------------------
    # Team-strength decay half-life, in weeks. Matches the projection model's
    # 4-game player-history half-life so "recent form" means the same thing
    # everywhere (methodology §4.1 rationale).
    team_strength_decay_half_life_weeks: float = 4.0

    # --- methodology §5, row 7 / §4.3 --------------------------------
    # contend needs a decay-weighted points-for percentile at or above this,
    # against the other 11 teams.
    contend_points_for_percentile: float = 60.0

    # --- methodology §5, row 8 / §4.3 --------------------------------
    # rebuild needs a percentile at or below this.
    rebuild_points_for_percentile: float = 35.0

    # --- methodology §5, row 9 / §4.3 --------------------------------
    # The signal is withheld ("too-early") before this week — earlier data is
    # too thin (methodology §4.3).
    contend_signal_start_week: int = 5

    # --- methodology §6 Q3 (concrete reading; ADR-0009) --------------
    # contend also needs season-rest playoff odds at or above this floor
    # ("within striking distance of a seed"); rebuild also needs playoff odds
    # at or below the low floor.
    striking_distance_playoff_odds: float = 0.25
    low_playoff_odds: float = 0.10

    # --- season-rest simulation (no §5 row; §4.3 names the sim) ------
    # Trial count for the playoff-odds simulation. Fixed + seeded, so identical
    # state gives identical odds (matches issue #10's 10,000-trial head-to-head
    # and the spec's determinism requirement).
    playoff_sim_trials: int = 10_000
    # Default RNG seed for the season-rest sim. Overridden per snapshot in
    # practice (``team_outlook(..., playoff_sim_seed=seed_from_snapshot_id(id))``)
    # so a snapshot's odds are stable across reloads, the same way the
    # head-to-head sim is seeded (ADR-0007).
    playoff_sim_seed: int = 0

    # --- methodology §5, row 10 / §4.4 -----------------------------
    # Dead Parrots starters on bye at one position: warn at this many, critical
    # at the critical count or more (or any week a legal healthy lineup cannot
    # be fielded). Fixed (methodology §5, row 10 "how to revisit: fixed").
    bye_crunch_warn_count: int = 2
    bye_crunch_critical_count: int = 3

    def __post_init__(self) -> None:
        rebuild_pct = self.rebuild_points_for_percentile
        contend_pct = self.contend_points_for_percentile
        if not 0.0 <= rebuild_pct <= contend_pct <= 100.0:
            raise ValueError(
                "need 0 <= rebuild_points_for_percentile "
                "<= contend_points_for_percentile <= 100"
            )
        low_odds = self.low_playoff_odds
        strike_odds = self.striking_distance_playoff_odds
        if not 0.0 <= low_odds <= strike_odds <= 1.0:
            raise ValueError(
                "need 0 <= low_playoff_odds <= striking_distance_playoff_odds <= 1"
            )
        if self.bye_crunch_warn_count < 1:
            raise ValueError("bye_crunch_warn_count must be >= 1")
        if self.bye_crunch_critical_count <= self.bye_crunch_warn_count:
            raise ValueError(
                "bye_crunch_critical_count must exceed bye_crunch_warn_count"
            )
        if self.playoff_sim_trials < 1:
            raise ValueError("playoff_sim_trials must be >= 1")


DEFAULT_STRATEGY_PARAMS = StrategyParams()
"""The signed-off methodology defaults — what the strategy layer uses unless
overridden."""
