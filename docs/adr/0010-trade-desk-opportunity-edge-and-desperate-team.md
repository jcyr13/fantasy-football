# Trade Desk: opportunity score, rank-space trade edge, and the desperate-team composite

Issue #13 asks for a function over assembled weekly league state producing an
**opportunity score** per player, **buy-low / sell-high** candidates, a
**market-value proxy** and a **trade edge** with a minimum-edge filter, a
**desperate-team ranking** of the other 11 managers, and a **countdown to
November 28**. `docs/methodology.md` §4.5–§4.9 defines each formula and §5 rows
11–12 name the two tunables; the §7 sign-off accepted §6's review answers "as
documented", which is where the two open numbers (the edge tier and the
opportunity-composite weights) are pinned. This ADR records the choices the
methodology left to the build. Vocabulary is CONTEXT.md's ("Opportunity score",
"Fantasy points allowed to position", "Consensus feed").

> **ADR numbering.** `0009` is claimed by the in-review Team Outlook layer
> (issue #12, PR #31); the two branches were built in parallel off `master`.
> This ADR takes `0010` to avoid the collision.

## Decision

**1. The Trade Desk layer defines its own input vocabulary, a sibling of the
Team Outlook layer's `LeagueState`, not a shared type.** Issue #13 is blocked
only by #7 (Yahoo pull) and #9 (projection model); it is not blocked by #12.
`TradeDeskState` carries what §4.5–§4.9 need — a trade-relevant player universe
with scored history + `UsageSnapshot`s, a per-player external market rank and
model rest-of-season points, and the other 11 teams with record / points-for /
roster birthdates / bye weeks. Like `project` taking a resolved
`consensus_points` rather than the feed, the layer does no I/O and never imports
the consensus package. Issue #16 (assembled weekly view) is where
`TradeDeskState` and `LeagueState` are reconciled into one assembled object.

**2. Opportunity score is one decay-weighted usage composite plus two trend
slopes, computed over the games that carry usage data.** The composite is the
equal-weighted mean of snap share, target share, route participation and
red-zone share (methodology §4.5; §6 Q6 accepts equal weights — the same four
weights `ProjectionParams` already uses). `opportunity_trend` and
`output_trend` are the projection model's `weighted_slope` (decay-weighted
least squares, per game) of the composite series and of the fantasy-points
series. Both series are restricted to games with a `UsageSnapshot` so the
opportunity signal and the output signal cover the **same window**, as §4.5
requires; a usage-less big-points week does not move the output trend without a
matching usage reading. A player with fewer than two usage games gets an
all-zero score and cannot be a candidate. The 4-game decay half-life matches
the projection window (§5 row 1).

**3. Buy-low / sell-high is a pure trend comparison, gated by roster
ownership.**

| flag | trend test | ownership |
| --- | --- | --- |
| buy-low | `opportunity_trend ≥ up` **and** `output_trend ≤ lag` | **not** on Dead Parrots |
| sell-high | `output_trend ≥ spike` **and** `opportunity_trend ≤ flat` | on Dead Parrots |

`up` / `flat` / `spike` / `lag` are the one knob §5 puts no number on (§4.6
only says "trending up" / "flat or declining" / "spiking" / "lags"). Each is an
**absolute bar** on its own series' decay-weighted slope — a deliberate
simplification of the relative reading ("output lags *the opportunity trend*"),
which would need a share→points scale factor the projection model only carries
internally (`opportunity_trend_sensitivity`, methodology §3.4). "Opportunity
flat or declining" is genuinely absolute in §4.6; "output lags" is read here as
"output is not itself climbing", which excludes a player already producing more
each week — arguably the right call, since the market is not badly mispricing a
riser. Defaults (`0.01` / `0.005` share-per-game, `1.5` / `0.5`
points-per-game) are placeholder magnitudes on each series' natural scale, in
`TradeParams`, pinned by behaviour tests, and swap in cleanly once tuned — the
same treatment as ADR-0006's residual priors and ADR-0008's threshold cutoffs;
moving to the relative comparison is the documented tuning path. Ownership gates
the two lists because a buy-low target is a *rival's* player to acquire and a
sell-high target is a Dead Parrots player to move.

**4. The trade edge is computed in positional-rank space.** The market-value
proxy is the player's external consensus **rest-of-season positional rank**
(§4.7), supplied on `TradePlayer.market_ros_rank`. The model's rank is
`TradePlayer.model_ros_points` — projection-model rest-of-season points, already
opportunity-adjusted upstream (methodology §3.2/§3.4: the projection mean *is*
opportunity-driven) — ranked within the player's role across the state's player
universe (1 = best). The layer does **not** re-apply an opportunity adjustment
here; doing so would double-count §3.4. `trade_edge = market_rank − model_rank`,
signed: positive means the model rates the player above the market (the buy-low
direction), negative means below (sell-high). The surfacing threshold is §6 Q4
as documented — **12 rank places at RB/WR, 6 at QB/TE** — with K/DEF/IDP taking
the same 6 (rarely trade chips, but a 6-place gap is a full tier at a shallow
position). A candidate is surfaced only when the **unweighted** directional edge
`|trade_edge|` reaches the role's tier.

**5. The sell-high weighting scales the ranking priority only, never the
threshold.** §4.6 says sell-high is "weighted up" for injury risk or a hard
upcoming schedule "because the market is slowest to price those in"; §4.8 says a
sub-tier edge "is noise and is hidden", unconditionally. Where the two pull
against each other, §4.8's hard filter wins: the surfacing test is on the raw
`|trade_edge|` (decision 4). The weight — a multiplier
`1 + injury_bonus·injury_risk + schedule_bonus·hardness` on the sell-high side
(`1.0` for buy-low), where `hardness` ramps `0 → 1` as the upcoming opponent's
fantasy-points-allowed-to-position (same §3.5 data) falls from parity to
`hard_schedule_ratio` (0.9) of the league average — scales `priority`, the sort
key, and is surfaced on the candidate (`sell_high_weight` + a reason line). So
injury / schedule risk pushes a sell-high *up the list* and is visible, but
cannot manufacture a candidate the rank gap does not support.

**6. The desperate-team composite is four min-max-normalized components, equally
weighted.** Per §4.9 / §6 Q5. Raw components per rival: sub-.500 severity
(`games_below_.500 / games_played`, ties neutral); inverted league points-for
percentile (`1 − pct/100`, the §4.1 decay-weighted points-for ranked against the
**full 12-team league**, Dead Parrots included, hence `dead_parrots_points_for`
on the state); mean roster age from nflverse birthdates at `as_of_date` (spots
with no birthdate — team DEF — are skipped; a rival with *no* birthdates at all
scores a neutral `0.5` on the age component, not the youngest end); and a
bye-crunch count of rostered players whose bye is still ahead. Each raw
component is min-max scaled to `[0, 1]` **across the 11 rivals** (an all-equal
component contributes 0; the age scale is fit over the rivals that have data),
the weighted sum is the score, and the top
`desperate_surface_count` (3) are surfaced. A surfaced team's `reasons` are the
plain-language `detail` of every component at or above `0.5` normalized, most
extreme first.

**7. The bye-crunch component is a roster-wide count, not the §4.4 grade.** §4.9
point 4 says "§4.4 applied to their roster", but §4.4 grades *starters* on bye
and needs a legal-lineup check, and a rival's starter designations are not in
the Yahoo pull. The component counts rostered players with an upcoming bye
instead — a defensible proxy for "how pinched is their roster about to get",
normalized alongside the other three.

**8. The countdown is a plain snapshot-dated day difference.**
`date(state.season, 11, 28) − state.as_of_date` in days; negative and
`is_past=True` once the deadline has passed.

## Why

- **Rank space for the edge, not points.** §4.8 offers either; §6 Q4's accepted
  answer is stated in rank places ("≥ 12 at RB/WR, ≥ 6 at QB/TE"), and "one
  positional tier" is inherently a rank concept. It also sidesteps needing the
  model and the consensus feed to agree on a points scale.
- **Restricting both trend series to usage games** is the literal reading of
  §4.5's "over the same window" and stops a fluke box score (garbage-time TD,
  no snap data) from reading as a real output spike.
- **Min-max within the rival set** gives §4.9's "equally-weighted" a concrete
  meaning without inventing a cross-component scale; it is a documented review
  item (§5 row 12) and swaps out if the equal weighting is revisited.
- **Points-for percentile against all 12 teams**, not just the 11 rivals, so the
  component means the same thing as team strength (§4.1) — a rival that is
  merely the best of a weak field still reads as low if the whole league is
  weak relative to Dead Parrots.
- **The weighting lifts borderline sell-highs on purpose.** "Weighted up …
  because the market is slowest to price those in" is a statement that these
  candidates should surface *more* readily, not just rank higher once surfaced.

## Consequences

- Pure functions, no I/O, no numpy; reuses `projection.decay_weights` /
  `weighted_mean` / `weighted_slope` so "recent form" is one implementation
  across the projection model, the Team Outlook layer, and here.
- The trend slopes, the sell-high bonuses, `hard_schedule_ratio`, and the
  `0.5` reason threshold are placeholder magnitudes in `TradeParams`, pinned by
  tests, tunable without a code change. Only the §6-accepted numbers (edge
  tiers, equal composite weights, equal desperate weights, Nov 28) are pinned
  as methodology.
- `model_ros_points` is ranked within whatever player universe the caller puts
  on the state — a thin universe yields optimistic model ranks. Issue #16 is
  responsible for handing the layer a full positional pool.
- `TradeDeskState` duplicates several `LeagueState` fields (records, weekly
  points-for, bye data). This is deliberate for an independently-shippable
  ticket and is the explicit merge point for issue #16.

## Considered alternatives

- **Build on the Team Outlook branch and reuse `LeagueState` / `team_strength`
  / `bye_crunch_map`.** Rejected: #13's declared blockers are #7 and #9, not
  #12; #12 is unmerged and in review. The desperate-team read needs
  *per-rival* points-for percentile and a roster-wide bye count anyway, neither
  of which the Dead-Parrots-shaped Team Outlook functions expose. Issue #16
  reconciles the two input shapes.
- **Trade edge in projected-points terms.** Rejected: §6 Q4's accepted answer is
  in rank places, and it would couple the filter to a model-vs-consensus scale
  calibration that does not exist yet.
- **Opportunity composite weighted toward targets/routes for pass-catchers.**
  Rejected for v1: §6 Q6 accepts equal weights; revisit against backtests.
- **The full §4.4 bye grade for rivals.** Rejected: needs starter flags the
  pull does not provide (see decision 7).
- **Letting the sell-high weight scale the surfacing filter** (so injury /
  schedule risk can pull a sub-tier edge over the line). Rejected: §4.8 says a
  sub-tier edge "is noise and is hidden" with no exception, and it is the
  sharper, more testable rule. The weight still raises `priority` and is
  surfaced on the candidate, so "weighted up" is honoured for everything that
  clears the gap on its own.
- **A relative buy-low / sell-high test** (`output_trend` vs `opportunity_trend`
  on a common scale). Rejected for v1: the share→points conversion lives inside
  the projection model (§3.4) and exposing it here is scope. The absolute bars
  are a documented, tunable stand-in (decision 3).
- **Team-level roster age floored to `0.0` when no birthdates are known.**
  Rejected: `0.0` reads as "youngest / least age-desperate", the opposite of
  "unknown". A neutral `0.5` leaves the composite unmoved by a data gap.
