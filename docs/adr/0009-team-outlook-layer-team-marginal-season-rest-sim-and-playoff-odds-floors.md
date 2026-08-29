# Team Outlook layer: a team-marginal season-rest simulation, and playoff-odds floors for "striking distance" / "low odds"

Issue #12 asks for a pure function over an assembled weekly league state
producing four advisory reads — team strength, expected wins, a
contend/rebuild/hold signal from ~Week 5, and a bye-week crunch map — none
recommending a transaction. `docs/methodology.md` §4.1–§4.4 defines every
formula and §5 rows 6–10 pin their parameters; the sign-off (§7) accepts them
"as written" and accepts "all answers to the §6 open questions as documented".
Two things the methodology names but does not fully pin down are settled here.
Vocabulary is CONTEXT.md's ("Team strength", "Expected wins", "Contend /
Rebuild / Hold signal", "Bye-week crunch").

## Decision

**1. The strategy layer is pure over an assembled `LeagueState`.** The 12 teams
with their scored weekly points-for and head-to-head records, the remaining
regular-season schedule, the Dead Parrots roster (position + NFL bye + starter
flag + season-availability) for the bye map, and one per-team weekly points
forecast for the season-rest sim. No I/O, no nflverse column names — whoever
runs the assisted pull and the projection model assembles it, exactly as
`project` consumes `PlayerHistory` / `OpportunityMetrics` rather than raw data
(methodology §2).

**2. Team strength is a decay-weighted mean of points-for, ranked as a
percentile against the other 11.** `weighted_mean` over the team's completed
weekly points-for with `decay_weights(n, half_life=4 weeks)` — reusing the
projection model's decay helpers so "recent form" is computed one way in the
app (methodology §4.1). The percentile is the standard percentile-rank
convention against the **other 11 teams only**: `(count strictly below + 0.5 ·
count tied) / 11 · 100`. Record is never read for this number.

**3. Expected wins sums each completed week's beaten-fraction; the exact
fraction is accumulated, only reported fields are rounded.** For each week Dead
Parrots have a score, the fraction of the other teams that *also scored that
week* whom their total beat (a tie counts a half). The season total is summed
from the unrounded fractions so per-week rounding never compounds. Actual wins
counts a tie as a half so it sits on the same scale; `luck = actual − expected`.

**4. Playoff odds come from a season-rest simulation over *team-level*
marginals.** The methodology (§4.3) names "a season-rest simulation that plays
the remaining schedule out using the projection model". The seam here is a
`TeamScoringForecast` per team — `mean` / `sigma` / `skew`, the same
Cornish-Fisher shape the projection model reports and the head-to-head sim
samples (ADR-0006) — aggregated **upstream** to the team's likely starting
lineup. The sim walks the remaining schedule trial by trial with one seeded
`random.Random`, draws each team's weekly total from its forecast, decides each
matchup (a tie splits the win), adds simulated wins to the banked record, ranks
by `(wins, then total points-for)`, and counts a team in the top
`state.playoff_team_count` as having made the playoffs. Playoff odds is that
fraction over `playoff_sim_trials` (default 10,000, matching the head-to-head
sim). The seed is `params.playoff_sim_seed`, overridable per snapshot via
`team_outlook(..., playoff_sim_seed=seed_from_snapshot_id(id))` so a snapshot's
odds — and therefore its signal — are stable across reloads (ADR-0007).

**5. "Within striking distance of a seed" and "low playoff odds" are floors on
that sim's odds.** Methodology §6 open question 3 asks whether "striking
distance" means "within N games of the 6-seed" or "a playoff-odds floor". This
ADR fixes it as a playoff-odds floor, read straight off the sim the methodology
already requires for the signal:

- **contend** — points-for percentile `≥ 60` **and** playoff odds `≥ 0.25`
  (`striking_distance_playoff_odds`);
- **rebuild** — points-for percentile `≤ 35` **and** playoff odds `≤ 0.10`
  (`low_playoff_odds`);
- **hold** — anything else, including a hot-but-doomed or cold-but-alive team
  the qualifier catches.

Both floors are `StrategyParams` fields, placeholder magnitudes pinned by
behaviour like the sim's correlation shares (ADR-0007). Before
`contend_signal_start_week` (5) the signal is `"too-early"` and the inputs are
still reported.

**6. The signal never recommends a transaction — enforced, not just intended.**
`ContendRebuildHold.recommends_transaction` is a frozen `False`;
`__post_init__` raises if it is ever constructed `True`. Methodology §4: "None
of them recommends a transaction."

**7. The bye-week crunch map counts *starters* on bye per role, and separately
checks a legal lineup can be fielded from the whole roster.** For each upcoming
week (`current_week … regular_season_weeks`): count roster players flagged
`is_starter` whose NFL bye is that week, by canonical role. Grade **warn** at 2
at a role, **critical** at 3+ *or* when `can_field_legal_lineup` is false for
the roster minus that week's byes minus season-unavailable players. The
new `deadparrots.lineup.can_field_legal_lineup` primitive answers "is some
`slots.size` subset of this pool a legal lineup" by checking each
`role_count_distributions()` vector against the pool's per-role counts — the
same legality basis `enumerate_lineups` uses, without needing `SimPlayer`
marginals.

## Why

- **Team-level marginals over wiring the full projection model into the season
  sim.** The projection model produces per-player marginals; summing a team's
  likely-lineup marginals to a `(mean, sigma, skew)` is a caller
  responsibility, the same division of labour as the head-to-head sim taking
  `SimPlayer`s rather than computing them. It keeps the strategy layer pure and
  fixture-testable (acceptance criterion 5) and means the season sim has one
  well-defined input, not a transitive dependency on every projection knob.
- **A playoff-odds floor over "within N games of the 6-seed".** The odds floor
  needs no separate tie-break model of the standings race, it already folds in
  strength of remaining schedule and games left, and it is the number the UI
  shows anyway. "N games back" would double-count what the sim computes.
- **Reusing the decay helpers and the Cornish-Fisher shape** keeps "recent
  form" and "a weekly scoring distribution" defined once across the projection
  model, the head-to-head sim, and this layer.
- **Enforcing `recommends_transaction=False`** makes the advisory-only contract
  a type-level fact rather than a convention a later edit could quietly break.

## Consequences

- Pure-Python, no numpy. The season-rest sim is `trials × remaining_matchups`
  Gaussian draws — ~10,000 × ~40 for a mid-season 12-team league, well under a
  second.
- **Common random numbers are *not* applied across teams in the season sim.**
  Opposing teams in a matchup are drawn independently; game-script correlation
  between the two sides is left to the head-to-head sim (methodology §3.9). This
  is a documented simplification — it slightly overstates the variance of a
  single matchup's margin but does not bias playoff odds over a full remaining
  schedule.
- Playoff seeding is league-wide top-N by `(wins, points-for)`. RIP TIDE's two
  **divisions** are carried on `LeagueTeam.division` but do not yet affect
  seeding (no division-winner guarantee). If the league's real tiebreak rules
  matter for a borderline team, that is a follow-up.
- The thresholds (`60` / `35` / `0.25` / `0.10`), the 4-week half-life, and the
  Week-5 start are `StrategyParams` fields transcribed from methodology §5;
  `test_strategy_params.py` fails CI if they drift from the doc.
- `team_outlook` consumes a fully assembled `LeagueState`; building one from the
  Yahoo pull, the scoring engine, and the projection model is downstream
  (issue #16). Issues #13 and #14 also read this `LeagueState` shape.

## Considered alternatives

- **Run the real projection model inside the season-rest sim.** Rejected for
  v1: it makes the strategy layer depend on the entire projection pipeline and
  its inputs, and the acceptance criterion is a hand-built fixture. The
  team-marginal seam can be fed by the projection model without the layer
  knowing.
- **"Within N games of the 6-seed" for striking distance.** Rejected: needs a
  standings-race model the odds sim already subsumes, and is a worse UI number.
- **Percentile against all 12 teams (including Dead Parrots).** Rejected:
  "against the other 11" is the methodology's wording and keeps a team from
  being ranked against itself.
- **Counting every rostered player at a position toward the bye grade, not just
  starters.** Rejected: methodology §4.4 says "starters"; bench depth on bye is
  captured by the separate `can_field_legal_lineup` check, which is what
  actually decides whether the week is playable.
- **A soft/continuous contend score instead of three labels.** Rejected: the
  methodology specifies a three-way signal with a deliberate neutral band; a
  score invites over-reading noise near the median.
