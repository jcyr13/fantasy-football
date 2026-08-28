# Lineup recommendation by direct win-probability optimization

The PRD describes risk tolerance as a rule: when favored, optimize the lineup's floor; when underdog, optimize its ceiling. We are instead recommending the lineup that **directly maximizes `P(win)`** against the week's opponent, estimated by head-to-head Monte Carlo over both lineups' correlated scoring distributions. Safe-when-favored and boom-or-bust-when-underdog then emerge from the math rather than from hand-set thresholds, and respond smoothly to *how* favored the team is.

## Considered Options

- **Threshold-switching** (favored >65% → optimize P10; underdog <40% → optimize P90; else median) — simpler to explain, but the cutoffs are arbitrary, behavior jumps at the boundary, and "best floor" is not identical to "best chance to win". Kept as a user-selectable toggle, not the default.
- **Direct `P(win)` optimization** — chosen as the default recommendation engine.

## Consequences

- Requires a trustworthy head-to-head simulation; a biased projection model produces a confidently wrong win probability. The methodology doc and scoring-engine validation gate exist partly to protect this.
- The recommendation is less self-explanatory ("sim says 58.3%"), so the dashboard always shows the favored/underdog read and the explicit floor and ceiling lineups alongside it as context.
- The four strategic layers hang off this win-probability estimate, so changing it later is expensive.
