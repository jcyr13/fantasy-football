# RIP TIDE Projection & Strategy Methodology

**Status: APPROVED — signed off by John on 2026-08-29 (see §7).** Recommendation
logic (ticket #8 onward) may now proceed on this model. See issue #6.

This document is the written, reviewable definition of two things:

1. the **projection model** — how a player's weekly fantasy-point distribution
   (floor / projection / ceiling) is produced; and
2. every **strategic-layer formula** — team strength, expected wins,
   contend/rebuild, bye-crunch grades, buy-low/sell-high, market-value proxy,
   trade edge, and the desperate-team read.

Every default parameter is stated here with a rationale. The rationales are
**proposed**; accepting or changing them is the purpose of the review.

Vocabulary follows [`CONTEXT.md`](../CONTEXT.md). The governing decisions are
[ADR-0002](adr/0002-win-probability-by-direct-optimization.md) (recommend by
direct win-probability optimization) and
[ADR-0003](adr/0003-python-for-numeric-logic-react-presentation-only.md) (all
numeric logic in Python).

---

## 0. Why this document exists before the recommendation logic

ADR-0002 recommends the lineup that directly maximizes `P(win)`, estimated by
Monte Carlo over both lineups' projected distributions. **A biased projection
produces a confidently wrong win probability**, and all four strategic layers
hang off that same estimate. The scoring-engine validation gate protects the
*points* math; this document and its sign-off protect the *projection* math.
Both must be settled before anything consumes them.

---

## 1. Scope and non-goals

**In scope:** the mean/shape projection method, the trailing-window decay, the
matchup and opportunity adjustments, thin-history and low-confidence handling,
and all strategic-layer formulas with their thresholds.

**Not in scope (defined elsewhere):**

- The **scoring engine** — `(stat rows, league ruleset) → points per
  player-week`. Its rules and its hard 0.00 validation gate are in the v1 spec
  and `CONTEXT.md`; this document treats scored points as a trusted input.
- The **head-to-head Monte Carlo** — trial count, common-random-numbers, the
  QB-to-pass-catcher and game-script **correlation model**, `P(win)`, gap
  drivers, swing players. That is the simulation's specification (ticket for the
  simulation/optimizer). This document produces the per-player marginal
  distributions the simulation samples; it does not define the joint.
- **Lineup legality / enumeration** — slot rules live with the optimizer.

---

## 2. Upstream inputs

| Input | Source | Notes |
| --- | --- | --- |
| Scored player-weeks (historical) | scoring engine over nflverse `player_stats` / `pbp` | RIP TIDE rules; the validated points series the model learns from |
| Opportunity metrics | nflverse `snap_counts`, `pbp`, `depth_charts` | snap share, target share, route participation, red-zone touches |
| Fantasy points allowed to position | scoring engine over nflverse `pbp`, per defense | decay-weighted; input to the matchup adjustment |
| Consensus feed | `ffanalytics` in the `rsidecar`, scored to RIP TIDE rules | cross-check for every player; the fallback projection for thin-history players. Sleeper public API is a Week-1 stopgap |
| Yahoo's own weekly projection | Yahoo assisted-pull scrape | displayed alongside the model number; never an input to it |

**Display rule:** the model's number is never shown alone. The consensus number
and Yahoo's number are always shown next to it.

---

## 3. The projection model

### 3.1 Output

For every rosterable player and week, the model outputs a **distribution of
weekly RIP TIDE fantasy points**, summarised as three points:

- **floor** = 10th percentile (P10)
- **projection** = 50th percentile (P50, the median)
- **ceiling** = 90th percentile (P90)

P10 < P50 < P90 is a hard invariant (asserted in tests).

### 3.2 Hybrid structure: opportunity mean × positional-residual shape

The projection is built in two independent pieces:

1. **The mean** comes from an **opportunity model**: expected usage (snaps,
   routes, targets, carries, red-zone looks) translated into expected RIP TIDE
   points via that player's efficiency and the position's scoring profile. This
   is deliberately a *role* forecast, not a *fantasy-output* forecast —
   opportunity is more stable week to week than fantasy points.

2. **The shape** comes from **position-level historical residuals**: the
   distribution of (actual − expected) fantasy points for all players at that
   position over a large historical sample. Wide-receiver weekly outcomes are
   right-skewed and high-variance; running-back less so; kicker and DEF
   different again. The residual distribution for the player's position is
   centred on the player's mean from step 1 and scaled to the player's
   projected volume.

**Rationale for splitting them:** a single blended estimate hides *why* a player
is boom-or-bust. Modelling the mean from opportunity and the spread from
positional history means the floor/ceiling gap reflects real, position-specific
outcome variance rather than a guessed error bar, and each half can be validated
on its own.

### 3.3 Trailing window and decay

Player-level history (both scored points and opportunity metrics) is weighted by
**exponential decay with a ~4-game half-life**: a game `g` games back gets
weight `0.5^(g / 4)`, i.e. a per-game decay factor of `0.5^(1/4) ≈ 0.841`.

| Games ago | Weight |
| --- | --- |
| 0 (most recent) | 1.00 |
| 1 | 0.84 |
| 2 | 0.71 |
| 4 | 0.50 |
| 8 | 0.25 |

**Rationale for 4 games:** NFL roles change on a monthly cadence — injuries,
depth-chart moves, scheme adjustments, snap-count ramps. A 4-game half-life
still puts ~75% of total weight on the last ~8 games (roughly half a season),
so it is responsive to a role change without discarding a stable veteran's
signal after one quiet week. **This is the single most impactful parameter and
the first one to revisit** (see §6).

### 3.4 Opportunity adjustment

The mean is nudged by the player's **trend** in the four opportunity signals —
snap share, target share, route participation, red-zone touches — measured as
the decay-weighted slope of each signal over the trailing window. A player
whose snap and target share are climbing gets a positive adjustment; a player
losing routes to a returning teammate gets a negative one.

The adjustment is applied to the mean **before** the matchup adjustment. It is
not separately capped, because it is bounded in practice by the range of the
underlying usage signals (all are shares in `[0, 1]`); an extreme swing there is
a real signal, not noise to clip.

### 3.5 Matchup adjustment and the ±20% cap

The mean is multiplied by a **matchup factor** derived from the opponent
defense's **fantasy points allowed to the player's position**, computed by the
scoring engine over nflverse play-by-play and decay-weighted (same 4-game
half-life). The factor is the opponent's allowed-rate relative to league
average, so an average matchup is ×1.00.

**The factor is clamped to the range `[0.80, 1.20]` — at most ±20%.**

**Rationale for ±20%:** defense-vs-position is a real but noisy and
slow-moving signal — a handful of games, contaminated by the quality of
offenses faced, injuries, and game script. Uncapped, an early-season sample
against two strong offenses can imply a ×1.6 factor that is mostly noise. ±20%
is roughly the largest matchup swing that survives in season-long backtests of
defense-vs-position as a predictor; beyond that the marginal signal is not worth
the added variance in the projection. Tests assert the factor never leaves
`[0.80, 1.20]`.

### 3.6 Thin history: the ≥4-game threshold, blending, low-confidence

A player needs **≥ 4 games in the current season** before their *own* residual
shape (§3.2 step 2) overrides the positional prior. Below that threshold:

- the shape is a **blend**: `w · own + (1 − w) · positional_prior`, with
  `w = games_this_season / 4` (so 0 games → pure prior, 3 games → 75% own); and
- the projection is flagged **low-confidence**.

**Rationale for 4 games:** four is the point at which a player's own
weekly-outcome spread starts to be estimable at all — with one to three games
the sample variance is dominated by luck and a single outlier. It also aligns
with the decay half-life, so "enough history to trust the shape" and "enough
history for the decay window to be meaningful" coincide.

### 3.7 Rookies and role-change players

Players with no usable current-season history in the relevant role — rookies,
players who changed teams or moved up a depth chart — **fall back to the
consensus feed plus positional priors** for the mean, with the positional prior
for the shape. These projections are always flagged low-confidence.

### 3.8 Early-season labelling (Weeks 1–3)

The 2026 season starts with **no 2026 game data**. All projections and
recommendations in roughly **Weeks 1–3** are explicitly labelled
**low-confidence and prior-driven** regardless of the per-player rule above. The
model self-corrects as current-season games accumulate; the label is removed
per player as they cross the §3.6 threshold.

### 3.9 What this model does *not* do

It produces **marginal** per-player distributions only. Player-to-player
correlation (a QB and his WR1 booming together; a game script lifting a whole
backfield) is applied by the **simulation**, not here. Feeding independent
marginals straight into a sum would understate a stacked lineup's variance —
which is exactly why the correlation model lives downstream.

---

## 4. Strategic-layer formulas

Each layer is a pure function over an assembled weekly league state (rosters,
scoring history, standings, schedule). None of them recommends a transaction;
each states the numbers behind its signal.

### 4.1 Team strength

**Definition:** Dead Parrots' **rolling points-for**, exponentially
decay-weighted with a **~4-week half-life**, expressed as a **percentile against
the other 11 teams'** identically-computed values.

**Rationale for points-for, not record:** win/loss in a 12-team H2H league is
heavily schedule- and luck-driven over a 14-week season. Decay-weighted
points-for is the health signal that a manager can actually act on. The 4-week
half-life matches the projection window so "recent form" means the same thing
everywhere.

### 4.2 Expected wins

For each past week, take the Dead Parrots' actual score and compute the fraction
of the other 11 teams it would have beaten that week; sum across weeks.
**Expected wins** is that sum. Comparing it to **actual wins** exposes how much
schedule luck has helped or hurt the record.

### 4.3 Contend / Rebuild / Hold signal

A weekly advisory from **~Week 5** onward (earlier data is too thin), from two
inputs: the team-strength percentile (§4.1) and **playoff odds** from a
season-rest simulation that plays out the remaining schedule using the
projection model.

| Signal | Condition (defaults) |
| --- | --- |
| **contend** | points-for percentile ≥ ~60th **and** within striking distance of a playoff seed on the rest-of-season sim |
| **rebuild** | points-for percentile ≤ ~35th **and** low playoff odds |
| **hold** | anything in between |

**Rationale for 60 / 35:** the league takes 6 of 12 to the playoffs, so the
50th percentile is the natural break. Pulling the thresholds to 60 and 35
leaves a deliberate neutral band around the median where the honest answer is
"hold" rather than flip-flopping a contend/rebuild call on noise. The
"striking distance" and "low odds" qualifiers stop a hot-but-doomed or
cold-but-alive team from getting a misleading label. **Exact cutoffs and the
"striking distance" definition are review items.**

### 4.4 Bye-week crunch grades

For each upcoming week, count Dead Parrots **starters** on bye by position:

| Grade | Condition |
| --- | --- |
| **warn** | 2 starters on bye at one position |
| **critical** | 3+ at one position, **or** any week a legal healthy lineup cannot be fielded |

**Rationale:** two at a position is usually coverable from the bench with a
downgrade; three, or an unfillable slot, forces a waiver move *now* rather than
later. The grade is the trigger for pre-emptive roster work.

### 4.5 Opportunity score (Trade Desk)

A single per-player **opportunity score** from nflverse: a decay-weighted
composite of snap share, target share, route participation, and red-zone
touches (same signals as §3.4, combined into one index). It is compared against
the player's **fantasy-points trend** over the same window.

### 4.6 Buy-low / Sell-high

| Flag | Condition |
| --- | --- |
| **buy-low** | opportunity score trending **up** while fantasy output **lags** |
| **sell-high** | fantasy output **spiking** while opportunity is **flat or declining** |

Sell-high is **weighted up** for a player carrying injury risk or a hard
upcoming schedule (from the same fantasy-points-allowed data as §3.5), because
the market is slowest to price those in.

### 4.7 Market-value proxy

There is no observable trade market in this league, so a player's market value
is proxied by **external consensus rest-of-season rank** (from the consensus
feed). This stands in for "what leaguemates believe the player is worth".

### 4.8 Trade edge and the surfacing threshold

**Trade edge** = the gap between the market-value proxy (§4.7) and the model's
**opportunity-adjusted projection** for the same player, expressed in
positional-rank terms.

A buy-low or sell-high candidate is **surfaced only when the edge clears
roughly one positional tier** (e.g. a player the market ranks as a mid WR3 whom
the model projects as a WR2). Below that, it is noise and is hidden.

**Rationale:** sub-tier "edges" are within the error bars of both the consensus
rank and the model. Requiring a full tier keeps the Trade Desk to a short list
of defensible targets. **"One tier" needs a concrete numeric definition per
position — a review item.**

### 4.9 Desperate-team read

Rank the other 11 managers by a **composite willingness-to-deal score** from
four equally-weighted components:

1. **sub-.500 record** — how far below .500;
2. **low points-for percentile** — §4.1 computed for that team;
3. **roster age** — mean age of rostered players from nflverse birthdates;
4. **their own bye-week crunch** — §4.4 applied to their roster.

Surface the **top 2–3** with the specific reasons that flagged them, as trade-
pitch context. **Component weights are currently equal and are a review item.**

### 4.10 Rest-of-season value / value over replacement

For free-agent ranking: a player's **projected points over the remaining
schedule** minus the projected points of a **freely-available replacement** at
the same position (the best player at that position currently on waivers). This
"value over replacement" is the sort key for the **rest-of-season** free-agent
list.

### 4.11 This-week streamer

A separate free-agent list for a current bye/injury hole, sorted by
**next-week ceiling (P90)** rather than rest-of-season value — especially at
K / DEF / IDP, where week-to-week matchup dominates. Answers "who do I plug in
*this* week", not "who do I hold".

### 4.12 Waiver-priority cost

Waiver priority is a reverse-standings queue with **no FAAB**. A successful
claim drops Dead Parrots to **last** priority. Each free-agent target is
annotated with whether the projected upgrade justifies spending that priority —
a qualitative flag driven by the size of the value-over-replacement gain and
the team's current queue position.

---

## 5. Parameter summary

| # | Parameter | Default | Where | Rationale (short) | How to revisit |
| --- | --- | --- | --- | --- | --- |
| 1 | Player-history decay half-life | **4 games** | §3.3 | responsive to role change, keeps ~½ season of signal | backtest projection error vs. 2–6 game half-lives on 2023–24 |
| 2 | Matchup adjustment cap | **±20%** | §3.5 | largest defense-vs-position swing that survives backtest noise | sweep cap 10–30%, compare calibration |
| 3 | Own-shape threshold | **≥ 4 games this season** | §3.6 | first point weekly spread is estimable; matches half-life | check low-confidence flag precision/recall |
| 4 | Thin-history blend weight | **`games / 4`, linear** | §3.6 | smooth prior→own handoff | compare to step function |
| 5 | Early-season label window | **Weeks 1–3** | §3.8 | no current-season data yet | fixed; remove per-player at threshold |
| 6 | Team-strength decay half-life | **~4 weeks** | §4.1 | matches projection window | tie to parameter 1 or set independently |
| 7 | Contend threshold | **~60th pct PF + in reach** | §4.3 | above median with a neutral band | tune on 2024/25 league outcomes |
| 8 | Rebuild threshold | **~35th pct PF + low odds** | §4.3 | below median with a neutral band | same |
| 9 | Contend signal start week | **Week 5** | §4.3 | earlier data too thin | fixed unless data says otherwise |
| 10 | Bye-crunch warn / critical | **2 / 3+** | §4.4 | 2 coverable, 3 forces a move | fixed |
| 11 | Trade-edge surfacing threshold | **~1 positional tier** | §4.8 | sub-tier edges are within error bars | define tier size per position (numeric) |
| 12 | Desperate-team component weights | **equal (¼ each)** | §4.9 | no prior reason to favour one | revisit after seeing real rankings |

---

## 6. Open questions for John's review

1. **Decay half-life (param 1 & 6).** Keep 4 games? Same value for player
   projections and team strength, or decouple them?
2. **Matchup cap (param 2).** ±20% as written, or wider/narrower? Symmetric?
3. **Contend / rebuild cutoffs (param 7 & 8).** Are 60 / 35 the right
   percentiles? What does "within striking distance of a playoff seed" mean
   concretely — within N games of the 6-seed? A playoff-odds floor?
4. **Trade-edge tier (param 11).** Give "one positional tier" a number: e.g.
   edge ≥ 12 ranks at RB/WR, ≥ 6 at QB/TE? Or express in projected-points terms?
5. **Desperate-team weights (param 12).** Keep equal, or weight record and
   points-for above roster age?
6. **Opportunity score composition (§4.5).** Equal weights on the four usage
   signals, or should targets/routes outweigh snaps for pass-catchers?
7. **Anything missing** — a formula or signal the dashboard needs that this
   document does not cover.

---

## 7. Sign-off

Per issue #6 and the v1 spec build sequencing, no recommendation logic
(ticket #8 onward) begins until this block is filled in.

- **Reviewed by:** John
- **Date:** 2026-08-29
- **Decision:** Approved as written. All defaults in §5 and all answers to the
  §6 open questions are accepted as documented; no changes requested.
- **Changes agreed during review:**
  - None. The parameter table in §5 stands as the starting values; each row's
    "how to revisit" column is the agreed path for tuning it later against
    backtests, not a blocker for the v1 build.
