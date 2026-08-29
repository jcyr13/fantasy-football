# Projection marginals: seeded Monte-Carlo over a positional-residual shape

Issue #9 asks for the function

```
(player_history, opportunity_metrics, consensus_feed, params, rng_seed)
  -> weekly RIP TIDE point distribution, summarised as floor P10 / projection P50 / ceiling P90
```

`docs/methodology.md` §3 fixes the *statistical* design — opportunity mean ×
positional-residual shape, a 4-game decay half-life, a ±20 % matchup cap, the
≥4-game own-shape threshold, the low-confidence rules. It deliberately does not
say how the distribution is *represented in code* or where the residual numbers
come from. This ADR records those two choices.

## Decision

**1. The marginal is a seeded Monte-Carlo sample, not a closed-form quantile.**
`project` centres a standardised residual shape on the adjusted mean, draws
`params.sample_count` points from `random.Random(rng_seed)`, sorts them, and
reads P10 / P50 / P90 by linear interpolation. `rng_seed` is threaded straight
through, so identical inputs and seed give byte-identical output (acceptance
criterion 5), and the same sampler will later feed the head-to-head simulation's
joint draw (methodology §3.9) rather than that code re-deriving a shape from
parameters.

**2. The residual shape is a two-parameter descriptor: `cv` and `skew`.**
`cv` is the residual standard deviation as a fraction of the player's projected
volume (so spread scales with the projection); `skew` is a Fisher skewness fed
to a first-order Cornish-Fisher term on a standard normal draw. This captures
the methodology's "WR weekly outcomes are right-skewed and high-variance, RB
less so, K and DEF different again" without committing to a full empirical
histogram we cannot yet fit.

**3. The positional priors ship as a placeholder table calibrated to the
methodology's qualitative ordering.** `POSITIONAL_RESIDUAL_PRIORS` in
`projection/residuals.py` has one `(cv, skew)` pair per position group. §3.2
says these come from "all players at that position over a large historical
sample"; that fit is a later ticket. The committed numbers only honour the
ordering the doc states (pass-catchers widest and most right-skewed, QB/K
tightest) and are pinned by *ordering* assertions, not magnitudes.
`prior_for_position` / the `priors` argument to `project` make the table a
drop-in replacement once fitted values exist — no interface change.

## Why

- **Seeded sampling over closed-form.** A parametric quantile would be faster
  but the downstream simulation has to sample anyway (for the QB↔pass-catcher
  and game-script correlation), and it must sample *the same shape* this module
  reports or the marginals and the joint disagree. One sampler, one seed
  discipline, is the smaller surface.
- **`cv` + `skew` over a histogram.** Two numbers per position are reviewable
  against §3.2's prose and cheap to re-fit. An empirical histogram would be more
  faithful but is unjustifiable before the historical residual fit exists, and
  it would bury the WR-vs-RB variance difference the methodology calls out.
- **Placeholder priors over blocking.** #9 blocks four downstream tickets. The
  shape math, the decay, the caps, the fallback and low-confidence logic, and
  the regression harness are all exercised now; swapping the seven `(cv, skew)`
  pairs later is a one-line change with a regenerated fixture.

## Consequences

- `ProjectionParams` carries a few knobs §5 does not list —
  `opportunity_trend_sensitivity`, the four equal usage weights,
  `residual_volume_floor`, `own_skew_clamp`. Each is an implementation constant
  §3 describes qualitatively; each is documented in `params.py` against its §3
  sentence and defaulted to match that prose. `test_projection_params.py` still
  pins every genuinely methodology-derived number. The opportunity trend
  multiplier itself is **not** clamped — §3.4 says the adjustment "is not
  separately capped", so `1 + sensitivity·slope` is applied as-is.
- Two undocumented-in-§3 safety nets, both surfaced in `reasons` and both
  low-confidence: `OPPORTUNITY_FALLBACK` (a rookie / role-change / no-history
  player with no consensus number — the opportunity mean stands in for the
  consensus mean §3.7 assumes), and `no-opportunity-forecast` (a player *with*
  history but no opportunity-model output this week — the consensus number
  anchors the mean while the player's own shape is still used). Both keep the
  weekly slate fully projected when a single upstream input is missing rather
  than raising mid-run.
- `own_skew_clamp = 1.0` keeps the Cornish-Fisher draw monotonic in `z` down to
  `z = -3`, well past the reported P10, so a noisy few-game skew estimate cannot
  reorder the quantiles. A final `min_quantile_gap` nudge after rounding makes
  `P10 < P50 < P90` unconditional.
- **The residual priors are not yet empirical.** Anything reading a
  floor/ceiling *gap* as calibrated (bet sizing, "how safe is this floor")
  should wait for the fitted table. The P50 and the flags do not depend on the
  prior magnitudes for a player past the ≥4-game threshold.
- Regenerating the golden fixture is `uv run python
  scripts/gen_projection_fixtures.py`; `test_projection_regression.py` fails on
  any unintended drift.

## Considered alternatives

- **Closed-form skew-normal quantiles, no RNG.** Rejected: `rng_seed` is in the
  signature for the simulation's benefit, and the sim must sample the identical
  shape; a second, closed-form path invites the marginal and the joint to drift.
- **Fit the positional residuals from nflverse now, inside this ticket.**
  Rejected: it is its own modelling task (sample construction, position
  bucketing, era weighting) and would hold up four downstream tickets for a
  refinement that swaps cleanly in later.
- **Take the consensus feed's own spread as the shape.** Rejected by
  `CONTEXT.md` ("Consensus feed" _Avoid_) and ADR-0005 — the consensus number is
  a mean only; the shape is this model's job.
