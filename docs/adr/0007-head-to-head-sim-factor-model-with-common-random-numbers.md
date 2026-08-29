# Head-to-head simulation: a factor-model copula sampled with common random numbers

Issue #10 asks for

```
(lineup_a_distributions, lineup_b_distributions, correlation_spec, rng_seed)
  -> P(win), summary stats
```

over 10,000 trials, with the seed derived from the weekly snapshot ID, **common
random numbers** shared across every candidate lineup and both sides, and
QB-to-pass-catcher and game-script correlation modelled rather than independent
draws. `docs/methodology.md` §3.9 fixes that the *joint* distribution lives here,
not in the projection model, but says nothing about how it is built. This ADR
records those choices. It builds on ADR-0006 (the projection marginal) and
ADR-0002 (recommend by direct win-probability optimization).

## Decision

**1. Correlation is a linear factor model, not a correlation matrix + Cholesky.**
Each player's latent standard-normal draw is

```
Z_i = team_coef_i · T_{team(i)} + game_coef_i · G_{game(i)} + idio_coef_i · E_i
```

where `T`, `G`, `E` are independent standard-normal *factor streams* keyed by
NFL team, NFL game, and player id. The coefficients are fixed by
`CorrelationSpec` as variance shares (`team_coef = sqrt(share)`, …) so that
`team_coef² + game_coef² + idio_coef² = 1`: `Z_i` is standard normal and each
player is sampled with exactly the marginal the projection model reports
(ADR-0006). Points are then `mean_i + cornish_fisher_unit(Z_i, skew_i) ·
sigma_i`. The Cornish-Fisher term is non-linear, so *realised* player-point
correlations are only approximately the shares — close enough for
floor/ceiling comparisons, and the shares are pinned by behaviour, not value.

**2. The marginal sampler and quantile reader are the projection model's,
reused verbatim.** `projection.model.cornish_fisher_unit` was split out of
`_skewed_unit`, and `_quantile` promoted to `projection.sample_quantile`, for
this; the sim imports both. One transform and one quantile method, each with one
definition — a second closed-form path was rejected in ADR-0006 for the same
reason. `sim_player_from_projection` reconstructs `sigma` with the projection's
own formula (`residual_cv · max(mean_final, residual_volume_floor)`), so the sim
and the reported floor/projection/ceiling are the same distribution.

**3. `sample_lineup_totals` is the common-random-numbers seam.** It returns one
lineup's per-trial totals as a pure function of `(members, rng_seed,
correlation, n_trials)`, and every factor stream is keyed by `(rng_seed, stable
id)` and cached. A player's per-trial points therefore do not depend on which
other players share the lineup, so:

- swapping one slot in a candidate lineup leaves every other slot's draws
  byte-identical — lineup-vs-lineup `P(win)` gaps are signal, not sampling
  noise;
- a fixed opponent yields a byte-identical opponent distribution on every call,
  across the thousands of calls the optimizer (issue #11) will make;
- both sides draw from one `rng_seed` namespace, so a shared NFL game couples
  them instead of two independent RNGs.

`simulate_head_to_head` is then just two `sample_lineup_totals` calls and a
comparison. `P(win)` is the fraction of trials where the Dead Parrots total
*strictly exceeds* the opponent's.

**4. The seed comes from the snapshot ID via BLAKE2b** (`seed_from_snapshot_id`),
not the salted built-in `hash`, so a snapshot reproduces its numbers across
processes and machines (spec user story 64).

**5. Game-script sign is by role.** Passing offence and the kicker load `+1` on
the shared game factor; the rushing attack, team DEF and IDP load `−1`. Opposing
pass-catchers in one game end up positively correlated (a shootout lifts both);
a rushing attack and the other side's passing game, negatively — the standard
game-stack / bring-back shape.

**6. Exactly the two channels issue #10 names, and their magnitudes are
placeholders.** `qb_stack_share = 0.35` (QB/WR/TE load on their NFL team's
offensive factor) and `game_script_share = 0.15` are calibrated to typical
fantasy-points correlations — a QB/WR1 stack lands near `qb_stack_share +
game_script_share ≈ 0.5` — and pinned by *behaviour* tests: stack widens the
lineup distribution, same-game players correlate, `P(win)` is monotonic in a
strictly better lineup. RB, K, team DEF and IDP ride the shared game factor
only; an RB-to-own-offence channel was considered and left out to keep the
model to the two requested channels. Magnitudes swap in cleanly once fitted,
exactly like the positional residual priors (ADR-0006).

## Why

- **Factor model over Cholesky.** A full correlation matrix + Cholesky factor
  depends on *which* players are in the lineup, so the same underlying draws
  would produce different latent values for a shared player when a different
  slot changes — reintroducing the sampling noise the common-random-numbers
  requirement exists to kill. The factor construction keys every draw to a
  stable id, is positive-semidefinite by construction, and needs no matrix
  algebra or a numpy dependency (the codebase has none).
- **Unknown team / game is not a failure.** A player with `nfl_team=None` or
  `game_id=None` gets a private, player-unique factor stream in place of the
  shared one: no correlation with anyone, marginal variance still exactly 1.
- **`sample_lineup_totals` exposed, not just `simulate_head_to_head`.** The
  optimizer needs per-lineup totals it can compare under shared randomness; the
  common-random-numbers property is also directly testable through it
  (concatenating two lineups equals summing their separate runs).

## Consequences

- Pure-Python `random.Random` sampling of ~10k trials × ~18 players is well
  under a second; `functools.lru_cache` on the factor streams makes re-running
  one matchup cheap.
- **Common random numbers hold only within a fixed `n_trials`.** A stream is
  keyed by `(seed, factor, n_trials)`, so a 2,000-trial Lineup-Lab preview and
  the 10,000-trial snapshot sim share nothing and their `P(win)` values can
  differ by sampling noise. Callers that need them to agree must run the same
  trial count.
- **The `lru_cache` is sized for one matchup, not a whole enumeration.** The
  issue #11 optimizer runs many candidate lineups against one opponent; it
  should hoist that opponent's `sample_lineup_totals` result and reuse it,
  rather than rely on a 256-entry cache to hold the shared streams across
  hundreds of candidates.
- The correlation magnitudes are not empirical. Anything reading a *coupling*
  strength as calibrated should wait for a fit; `P(win)`'s ordering and the
  monotonicity guarantee do not depend on the magnitudes.
- `cornish_fisher_unit` and `sample_quantile` are now public API of the
  projection package. Their behaviour is unchanged and still covered by the
  projection regression fixture.
- Gap-driver decomposition and swing-player variance ranking (issue #11) are
  *not* here — this ADR is the sim only. They will consume `sample_lineup_totals`
  output.

## Considered alternatives

- **Full correlation matrix + Cholesky.** Rejected: lineup-dependent, breaks
  common random numbers under a slot swap, and pulls in a linear-algebra
  dependency.
- **Gaussian copula with an empirically fitted joint.** Rejected for v1 for the
  same reason ADR-0006 defers the residual fit — it is its own modelling task
  and would block four downstream tickets.
- **A separate RNG per side.** Rejected: it cannot express a game that lifts
  both sides at once, and it makes lineup-vs-lineup comparisons noisier than
  they need to be.
- **Seeding from `hash(snapshot_id)`.** Rejected: `hash` is salted per process,
  so "repeated runs are identical" would hold only within one process.
