# Lineup optimizer: exhaustive enumeration scored by reusing the head-to-head sim under common random numbers

Issue #11 asks the optimizer to "exhaustively enumerate every legal lineup from
the non-IR roster" and, for each, report `P(win)`, `E[points]`, and
P10/P50/P90, then surface the max-P(win) lineup (the primary recommendation),
the max-EV lineup, the floor lineup, and the ceiling lineup, plus a per-slot
gap-driver decomposition and an opponent swing-player ranking. `docs/methodology.md`
§1 puts "lineup legality / enumeration" with the optimizer and says nothing
about how it is built; ADR-0002 fixes the recommendation as direct
win-probability optimization; ADR-0007 built the head-to-head sim with common
random numbers "across the thousands of calls the optimizer will make". This ADR
records the enumeration and scoring choices. Vocabulary is CONTEXT.md's
("Max-P(win) lineup", "Gap drivers", "Swing player", "Opponent likely lineup").

## Decision

**1. A lineup is a distinct *set of ten starters*, not a slot permutation.**
Putting a WR in the `W/R/T` flex versus a `WR` slot is the same ten players on
the field and the same weekly total, so it is one lineup here.
`enumerate_lineups` yields each legal starting set once. It works from
`LineupSlots.role_count_distributions()` — the fixed slots pin a base count per
role, each flex slot spreads its count across its eligible roles in every
`combinations_with_replacement`, and the fold gives every legal role-count
vector (RIP TIDE's single `W/R/T` yields exactly three: an extra RB, WR, or TE).
For each vector, the members are a `combinations` — not `permutations` — draw
from each role's pool. Distinct vectors differ in some role's count and a player
has one role, so no set is produced twice.

**2. Completeness is proven by brute force, not by argument alone.**
`is_legal_lineup` is an independent maximum-bipartite-matching
(Kuhn's algorithm) between players and individual slots. The enumeration test
takes a known 13-player roster, filters all `C(13,10)` subsets through
`is_legal_lineup`, and asserts the result equals `enumerate_lineups`'s output
exactly — same sets, none repeated. That cross-check is the acceptance
criterion of record.

**3. Every candidate is scored by *reusing* `sample_lineup_totals`, not a second
sim.** ADR-0007 guarantees a lineup's per-trial totals are the elementwise sum
of its players' individual per-trial contributions — a player is drawn the same
whoever it lines up beside. So the optimizer samples each distinct player once
(`sample_lineup_totals([player])`), caches the array, and adds the ten arrays
per candidate in the lineup's canonical (`player_id`-sorted) order. This
reproduces `simulate_head_to_head` **byte-for-byte** on the same seed and trial
count — a test asserts `p_win`, `mean`, and P10/P50/P90 are equal — while
sampling ~20 players instead of ~20 × thousands-of-candidates. The opponent's
totals are computed once and reused for the whole sweep, so
candidate-vs-candidate `P(win)` gaps are signal, not sampling noise.

**4. The four reported lineups are argmaxes over the one sweep**, on `p_win`,
`expected_points`, `p10`, and `p90`; `p50` is also tracked for the threshold
rule. Ties break on the lineup's sorted `player_id`s so a pick is deterministic
across runs.

**5. The favored→floor / underdog→ceiling threshold rule is a toggle, never the
default** (ADR-0002 "Considered Options"). `optimize_lineups` takes
`recommendation_engine="max-p-win"` (default) or `"threshold-rule"`;
`OptimizerResult.recommendation` returns the active one, and the gap drivers,
swing ranking, and full head-to-head are all computed for whichever that is.
The threshold rule reads the situation from the max-P(win) lineup's `p_win`:
`> 0.65` → the floor lineup, `< 0.40` → the ceiling lineup, else the best-P50
lineup. Both thresholds are parameters. The best-P50 lineup is not one of the
four named lineups — it is reachable only through `threshold_rule.evaluation`
in the coin-flip band.

**6. Gap drivers are an analytic per-slot mean difference.** Expected weekly
points are additive across a lineup and untouched by the correlation model, so
aligning the two legal lineups slot-for-slot (same-name slots ordered by
projection, so RB1 is the higher-projected back on each side) and differencing
the slot means gives a decomposition that sums *exactly* — `math.fsum` — to
`Σ dead-parrots means − Σ opponent means`. It matches the sim's `mean_margin`
up to Monte-Carlo error.

**7. Swing players are ranked by a drop-to-mean variance delta.** The outcome is
the margin `Dead Parrots total − opponent total`. A starter's swing
contribution is `Var(margin) − Var(margin with that starter pinned to its
mean)`, computed on the shared trial draws (common random numbers again). It
captures the starter's own variance *and* its covariance with the rest of the
matchup. A negative value — a starter that dampens outcome variance — is
reported as such; ranking is by the signed value, biggest first.

**8. The opponent lineup is built from the least-assumption source available,
and the source is surfaced.** Order:

- `yahoo-set` — the lineup Yahoo already shows, when complete, legal, and
  healthy. No assumption.
- `prior-week-heuristic` — last week's starters, minus anyone unavailable, holes
  filled by best available projection, then a **bounded** pass of *obvious*
  bench upgrades: a bench player must out-project the starter by ≥ 3.0 points
  and at most 3 such swaps are applied, so the result stays "last week's lineup,
  lightly corrected" rather than a rebuild. Every drop, fill, and swap is a
  `notes` line.
- `projection-heuristic` — no set or prior lineup exists (realistically only
  Week 1). The opponent is assumed to start their highest-projected legal
  lineup, which *is* optimal by projection. This is the one case the spec's
  "never assume their optimal lineup" cannot be honoured — there is nothing to
  anchor to — so it is labelled loudly, `notes` states it is a fallback and not
  a claim they play optimally, and every consumer (`OptimizerResult`) carries
  the assumption. The alternative, raising, was rejected as worse UX for a
  Week-1 matchup.

The assumption label rides on the result; a bare opponent sequence passed
straight to `optimize_lineups` is labelled `provided`.

## Why

- **Set-not-permutation** keeps the candidate count to what actually differs for
  a decision. A 15–16-player non-IR roster is ~500–1000 candidates; the flex
  never multiplies that by the number of ways to seat the same players.
- **Reusing `sample_lineup_totals`** is ADR-0007's stated plan ("hoist the
  opponent's result and reuse it"). It also means there is exactly one sim: the
  optimizer cannot drift from `simulate_head_to_head`, and the byte-for-byte
  test pins that.
- **Analytic gap drivers over a Monte-Carlo slot attribution.** The mean
  identity is exact and needs no trials; a sampled decomposition would carry
  noise that stops it summing to the total.
- **Drop-to-mean over a Shapley/variance-share decomposition.** Shapley over ten
  starters is `2^10` sub-lineups per player; the drop-to-mean delta is one extra
  variance evaluation per starter, reads directly as "how much does this player
  move the result", and needs no independence assumption.

## Consequences

- Pure-Python, no numpy. A deep roster (3400 candidates) at 10,000 trials is
  ~17 s on a laptop; a typical roster is a few seconds. This is a weekly-snapshot
  batch computation, not an interactive path — the Lineup Lab (spec stories
  12–15) will run far fewer candidates at a lower trial count.
- **Common random numbers hold only within a fixed `n_trials`** (ADR-0007). The
  optimizer threads one `n_trials` through the sweep, the final
  `simulate_head_to_head`, the gap drivers' sanity check, and the swing ranking,
  so they all agree. A lower-trial Lineup-Lab preview will not match a
  10,000-trial snapshot to the cent.
- The threshold-rule cutoffs (0.65 / 0.40) and the obvious-upgrade margin (3.0)
  are placeholder magnitudes, pinned by behaviour like the sim's correlation
  shares (ADR-0007) and the residual priors (ADR-0006). They are parameters and
  swap in cleanly once tuned on league outcomes.
- `is_legal_lineup` / `assign_slots` are general over any `LineupSlots`, but
  `RIP_TIDE_SLOTS` is the only one in the app — CONTEXT.md, "The tool models
  this league and no other".
- The optimizer consumes `SimPlayer` marginals and an opponent roster; wiring
  real projections and the prior weekly snapshot's starters into it is
  downstream (issue #16).

## Considered alternatives

- **Enumerate every legal slot assignment.** Rejected: multiplies identical
  starting sets by flex seatings, inflating the sweep with no decision value.
- **Branch-and-bound / LP instead of exhaustive.** Rejected: the issue asks for
  every lineup's numbers reported, `P(win)` is not separable across slots, and
  the exhaustive sweep is already fast enough for a batch job. Revisit only if
  roster sizes or trial counts grow.
- **A second, lighter simulation for the sweep.** Rejected: two sims drift.
  Reusing `sample_lineup_totals` is exact and already fast.
- **Shapley variance shares for swing players.** Rejected for v1 as `2^10` per
  starter for a number that reads the same as the drop-to-mean delta.
- **Assuming the opponent's optimal lineup as the primary path.** Rejected —
  CONTEXT.md ("Never assumed optimal") and spec story 3. It survives only as the
  labelled `projection-heuristic` fallback for the Week-1 no-history case (§8),
  where the alternative is to refuse to produce a matchup at all.
- **Summing the Monte-Carlo `E[points]` fields for the gap-driver total instead
  of the analytic means.** Rejected: the analytic `Σμ` identity is exact and
  needs no trials, so the decomposition sums to the cent; the MC means only
  estimate the same quantity and would leave a residual. `head_to_head.mean_margin`
  is the MC estimate of that same total, shown alongside.
