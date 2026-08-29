# Assembled weekly view: one reconciled `AssembledWeek`, the layers composed behind stable API contracts

Issue #16 is the reconciliation point the earlier ADRs deferred to it: #9's
projection inputs, #11's optimizer `RosterPlayer`, and the three sibling
strategic-layer states (`LeagueState` #12 / ADR-0009, `TradeDeskState` #13 /
ADR-0010, `WaiverState` #14 / ADR-0011) were each built pure over a hand-assembled
input, with every one of those ADRs naming issue #16 as "where the layers' input
shapes are reconciled into one". This ADR records how that reconciliation is
done, what raw data feeds it, where the v1 data is thin enough that a section is
computed from a **documented approximation**, and the shape of the HTTP surface
the six screens plus the ticker depend on.

Vocabulary is CONTEXT.md's throughout ("Weekly snapshot", "Assisted pull",
"Opponent likely lineup", "Data-freshness header").

## Decision

### 1. One assembled state: `deadparrots.weekly.AssembledWeek`

`assemble_week(...)` is the single adapter from raw pulls to a frozen
`AssembledWeek`. It is the only place in the backend that touches nflverse
column names *and* Yahoo normalized objects together. It produces:

- `dead_parrots_roster` / `opponent_roster` — `lineup.RosterPlayer` lists, each
  player carrying the `SimPlayer` marginal built from its `PlayerProjection`
  (`sim_player_from_projection`, ADR-0006), with `nfl_team` / `game_id` resolved
  from the schedule so the correlation model can form stacks;
- `player_projections` — the full `PlayerProjection` per resolved player, kept
  for the confidence flags and the UI drill-down;
- `league_state` / `trade_state` / `waiver_state` — the three sibling inputs,
  now built from one shared player-identity resolution and one shared scored
  history;
- `news_targets` — the Dead Parrots roster, the current opponent roster, and the
  free-agent shortlist (the top of the rest-of-season list), so the news poll's
  target provider (issue #15) finally gets its third bucket;
- `caveats` — a list of human-readable strings naming every section that used an
  approximation below. Every endpoint whose payload draws on one echoes the
  relevant caveats so nothing thin is presented as ground truth (PRD
  "explicit about methodology and confidence").

`assemble_week` does no I/O. A thin `WeeklyDataSources` provider (on
`app.state`) reads the latest archived Yahoo payloads and the nflverse parquet
views and hands `assemble_week` plain frames + normalized objects; the API
layer calls the provider per request. Before the first assisted pull the
provider raises and the weekly endpoints answer `503`, exactly as
`POST /api/yahoo/pull` already does without a browser source (issue #7).

### 2. Player identity: normalized-name match against the nflverse roster, best-effort

There is no shared key between a Yahoo scrape (display names) and nflverse
(`player_id` + `player_name` like `"J.Allen"`). `weekly.identity` builds a
resolver from the `rosters` frame: it indexes every `(normalized full name,
team)` and `(normalized "F.Last", team)` onto the nflverse `player_id`
(`gsis_id`), with `yahoo_id` used directly when the scrape ever carries it.
Normalization casefolds, strips punctuation and generational suffixes
(`Jr`/`Sr`/`II`/`III`), and collapses whitespace. A Yahoo team-DEF entry
(`"Cardinals"`) resolves to the team abbreviation.

A Yahoo player that does not resolve is **not dropped** — it keeps a synthetic
`yahoo:<slug>` id, has no scored history, and its projection falls back to the
Yahoo weekly projection as the mean (the same `CONSENSUS_FALLBACK`-style path
`project` already supports via `consensus_points`). Unresolved starters are
listed in `caveats`.

### 3. Scored history and the "expected" baseline

`weekly.scored_history` turns the nflverse `player_stats` frame into
`scoring.StatRow`s and runs the **validated engine** (`score_player_weeks`,
never a second implementation — ADR-0005) to get each player-week's RIP TIDE
`actual_points`. Team-DEF and IDP rows are scored on their own units.

`project` (#9) wants a `PlayerGame.expected_points` per historical game and an
`OpportunityMetrics.expected_points` for the target week — both from an
"opportunity model" that issue #9 consumed but no ticket has built. v1 uses a
**decay-weighted trailing mean of the player's own scored actuals** as that
baseline (same half-life as the projection model's shape decay). Consequences:
the residual series `actual − expected` is genuine week-to-week variation around
the player's recent form, so the model stays on its `PLAYER_HISTORY` shape path;
the mean is recency-weighted form, not a usage forecast. This is the single
biggest modelling approximation in v1 and is named in `caveats` on every
projection-backed section. A real opportunity model is a later ticket that
swaps `weekly.opportunity` without touching `project` or the layers.

`weekly.opportunity` fills `UsageSnapshot` (snap / target / route / red-zone
shares) from `snap_counts` + `player_stats` where the rows are present, `None`
otherwise — `project` already skips usage-less games in the trend slope.

### 4. League-wide weekly history: approximated from the standings season totals

The strategic layers need each of the 12 teams' RIP TIDE points **per completed
week**, the remaining head-to-head schedule, and a per-team scoring forecast.
None of that is on any of the four Yahoo pages (the matchup page is the current
week for two teams; standings is season aggregates). Until issue #17 persists a
real weekly snapshot per team, `assemble_week` approximates:

- **`weekly_scores`** — each team's standings `points_for` split evenly across
  the `current_week − 1` completed weeks. Team strength is a decay-weighted
  points-for **percentile** and expected wins is a rank-order statistic, so a
  flat split preserves the between-team ordering that drives both; it flattens
  the within-season *trend* and makes weekly expected-wins degenerate. Named in
  `caveats`.
- **`remaining_schedule`** — a divisional-aware round-robin over the remaining
  regular-season weeks, generated deterministically from the standings order.
  It feeds only the playoff-odds season-rest sim.
- **`scoring_forecasts`** — `mean` = the team's flat weekly points-for,
  `sigma` = `weekly_forecast_sigma_fraction × mean` (default 0.18, a placeholder
  magnitude pinned by a test like the sim's correlation shares, ADR-0007),
  `skew` = 0.
- **`optional real history hook`** — `assemble_week` takes
  `prior_team_weeks: Mapping[str, Mapping[int, float]] | None`. Issue #17 passes
  real per-week team totals here and the approximation is bypassed entirely.

The desperate-team read (#13 §4.9) needs all 11 rival rosters with birthdates;
v1 has only the current opponent's roster from the matchup page. `assemble_week`
supplies the rivals it can (opponent fully, the rest from standings record +
points-for with empty rosters). The read still ranks on the record and
points-for components; the roster-age and rival-bye components are zero for
teams with no roster. Named in `caveats`.

### 5. Endpoints — stable contracts, one Pydantic model per screen

All under `/api`. Read endpoints assemble on demand; the JSON is a frozen
Pydantic shape the frontend (issues #18, #19) codes against.

| Method & path | Screen / purpose |
| --- | --- |
| `GET /api/weekly` | This Week — opponent, likely lineup + assumption, both totals (floor/proj/ceiling) with the Yahoo cross-check, favored/underdog + win%, gap drivers, swing players, the recommended lineup with floor/ceiling/max-EV alongside, the threshold-rule alternative |
| `POST /api/weekly/lineup-lab` | Lineup Lab compute — a candidate lineup (start/bench/IR ids) in → total / floor / ceiling / win-prob out; illegal lineups marked with the reason |
| `GET /api/weekly/lineup-lab/auto` | best-floor and best-ceiling fills, side by side |
| `GET /api/free-agents` | Waiver / Free Agents — rest-of-season list, streamer list, waiver-priority standing, cutdown window |
| `GET /api/team-outlook` | Team Outlook — team strength, expected vs actual wins, contend/rebuild/hold + inputs, bye-crunch map |
| `GET /api/trade-desk` | Trade Desk — opportunity scores, buy-low/sell-high candidates, desperate-team read, Nov-28 countdown |
| `GET /api/news` | ticker items (bucketed), plus `all_sources_failed` |
| `GET /api/history` | weekly-snapshot history — **empty list + `pending: true` until issue #17** |
| `GET /api/freshness` | per-source last-success / age / state for nflverse, consensus, news, and Yahoo, plus the Yahoo staleness reminder |
| `POST /api/refresh` | "Refresh now" — runs the nflverse + consensus + news pulls, returns each outcome |
| `POST /api/refresh/{source}` | per-source refresh (`nflverse` / `consensus` / `news`) |
| `POST /api/yahoo/pull` | the assisted pull — unchanged from issue #7 |

`GET /api/weekly` carries a top-level `rng_seed` (`seed_from_snapshot_id` of
`"{season}-{week}"`) so the numbers are stable across reloads (user story #64)
and identical to what issue #17 will freeze.

### 6. What is real vs approximated in v1

Fully real from the pulls: This Week, Lineup Lab, gap drivers, swing players,
opponent-lineup assumption, the free-agent lists, waiver priority, the cutdown
window, bye-crunch, trade opportunity scores, the trade-deadline countdown,
news, freshness, the triggers. Approximated (and `caveats`-flagged): the
projection mean baseline (§3), team strength / expected wins / playoff odds /
the signal (§4), the desperate-team roster-age and rival-bye components (§4).

## Why

- **One `assemble_week`, not per-layer adapters.** The three layer states share
  a roster, a scored history, and a player-identity map; building them together
  is the only way the same player is the same id everywhere and the This Week
  lineup, the waiver hole detection, and the bye-crunch map agree.
- **Approximate, flag loudly, keep the seam.** The layers are already built and
  tested against their real input shapes. Feeding them a documented
  approximation now — with `prior_team_weeks` as the hook #17 fills — ships the
  screens without a second rewrite later, and `caveats` keeps the UI honest.
- **Assemble per request, no cache.** v1 has one user and the assembly is
  milliseconds of pure Python over small frames; a cache is complexity with no
  payoff, and issue #17's snapshot is the real persistence story.
- **Name-match identity, best-effort, non-dropping.** Perfect resolution needs
  the Yahoo API's ids (ADR-0001's later path). Until then a missed match
  degrades one player to its Yahoo projection rather than removing a starter and
  breaking lineup legality.

## Consequences

- `deadparrots.weekly` is the one impure-adjacent package (it still does no I/O,
  but it knows both vocabularies). The layers stay pure and untouched.
- Every approximation is one function in `weekly/` with a test and a `caveats`
  string; issue #17 deletes the league-history approximation, a later
  opportunity-model ticket deletes the projection-baseline one.
- The integration test (`tests/test_weekly_integration.py`) drives a
  self-consistent fixture world under `tests/fixtures/weekly/` from raw frames
  and Yahoo payloads through `assemble_week` → projection → simulation → every
  endpoint's JSON, asserting the contract shapes and the `rng_seed` stability.
- Response models are additive-only from here: fields may be added, never
  removed or retyped, without a new ADR.

## Considered alternatives

- **Block #16 on a real opportunity model and on #17.** Rejected: both are
  large, both have their own tickets, and the screens (#18/#19) are blocked on
  this one. The approximation + `caveats` + the `prior_team_weeks` hook is the
  smaller honest step.
- **Drop unresolved Yahoo players.** Rejected: removing a starter can make the
  opponent roster unable to field a legal lineup and silently changes the
  recommendation.
- **A materialized weekly cache in SQLite.** Rejected as premature; that is
  issue #17's immutable snapshot, not a performance cache.
- **One mega-endpoint returning every screen.** Rejected: the screens load
  independently and a Lineup Lab recompute must not re-run every strategic
  layer.
