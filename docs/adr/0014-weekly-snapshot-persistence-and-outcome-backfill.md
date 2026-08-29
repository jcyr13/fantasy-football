# Weekly snapshot persistence: an append-only capture, a one-shot outcome backfill, two tables so nothing is ever mutated

Issue #17 asks for an **immutable per-week record** of that week's projections,
lineups, recommendations, and strategic-layer outputs at the time they were
produced, with the **actual outcome backfilled** after games without touching
the original numbers, retained for the whole season and queryable per week. It
is the persistence story ADR-0013 §4 deferred: the `prior_team_weeks` hook on
`assemble_week` is fed from these records once a season has real per-week team
totals.

Vocabulary is CONTEXT.md's: a **Weekly snapshot** is this persisted record; the
**Assembled weekly view** (`assemble_week`) is rebuilt fresh per request and is
never itself persisted.

## Decision

### 1. The captured payload is the four screen contracts, verbatim

A snapshot's `captured` payload is the JSON of the four read endpoints for that
week — `GET /api/weekly`, `/api/team-outlook`, `/api/trade-desk`,
`/api/free-agents` — serialized from **one** `build_weekly_view(assembled)` so
the optimizer, the head-to-head sim and the three strategic layers all see the
same `AssembledWeek` and the same `rng_seed`. Those Pydantic models
(`api/schemas.py`) are already the stable, additive-only contract the frontend
codes against (ADR-0013 §5), and they already carry exactly what the ticket
lists: per-slot projections with floor/proj/ceiling, the recommended /
max-EV / floor / ceiling lineups, favored/underdog + win%, gap drivers, swing
players, team strength / expected wins / the signal, the trade reads, the
free-agent lists. Persisting the contract rather than a second bespoke shape
means the History screen (#19) renders a stored week with the same components
it renders the live week, and there is no third serialization to keep in step.

The per-endpoint serialization moved out of the route handlers into
`api/serialize.py` (`serialize_weekly_view`, `serialize_team_outlook`,
`serialize_trade_desk`, `serialize_free_agents`, plus `serialize_history_record`
and the `?engine=` resolver) so the capture path and the live routes share one
implementation. `serialize_weekly_view` gains one additive field,
`dead_parrots_current_lineup` — the Yahoo-set lineup per slot with its
projections, so the backfill (§3) can pair an actual with a frozen projection
for a player John started but the model did not pick.

### 2. Two tables — the immutable row is only ever `INSERT`ed

`weekly_snapshot` holds the capture: `snapshot_id` (`"{season}-{week}"`, the
same string `seed_from_snapshot_id` keys the sim off — ADR-0007), `season`,
`week`, `created_at`, `rng_seed`, and `captured` (the §1 JSON). It has
`UNIQUE(season, week)` and is written with `INSERT … ON CONFLICT DO NOTHING`:
**a re-run for a week that already has a snapshot is a no-op**, and
`save_snapshot` returns the row that is already there. There is no `UPDATE`
statement against this table anywhere in the code.

`weekly_snapshot_outcome` holds the backfill, one row per snapshot keyed by
`snapshot_id` as its primary key: `backfilled_at`, `dead_parrots_total`,
`opponent_total`, `result` (`win` / `loss` / `tie`), and `player_actuals` (a
JSON list of `{player_id, name, projected_points, actual_points, delta}` — one
per player in the recommended lineup, the Yahoo-set lineup, or the submitted
mapping, so a real starter the model did not pick is never silently dropped).
It too is `INSERT … ON CONFLICT DO NOTHING`; a second backfill for the same week
does not overwrite the first, and the endpoint answers `409` rather than
pretending it did.

Splitting the outcome into its own table makes immutability structural, not a
matter of discipline: the capture row has no nullable "actual" columns to
tempt an `UPDATE`, and "was this week scored yet?" is `LEFT JOIN … IS NULL`.

### 3. `build_outcome` is pure; sourcing the actuals is the caller's job

`snapshot/backfill.py::build_outcome(snapshot, *, dead_parrots_total,
opponent_total, player_actuals)` takes the two final totals and a
`{player_id: actual_points}` mapping, derives `result` from the totals, and
joins the actuals onto the union of the player ids the snapshot's recommended
and Yahoo-set lineups recorded plus any other id the mapping carries —
producing the `model-said` (the frozen projection mean, 0.0 for an id with no
frozen projection) next to `what-happened` (the actual, 0.0 for a frozen player
the mapping omits) per player. It does no I/O.

In v1 the `POST /api/history/{week}/outcome` endpoint takes those numbers in the
request body: this is a single-user "assisted" dashboard (CONTEXT.md
"Assisted pull"), and after Monday night John submits the week's finals the
same way he triggers a pull. Deriving them automatically from a post-games
nflverse `player_stats` pull is a later refinement that swaps the endpoint's
body for a read through `scored_games_by_player` — `build_outcome` does not
change when it lands.

### 4. Capture trigger: a weekly cron, plus an idempotent manual endpoint

`register_weekly_snapshot_capture` adds a Sunday-late-morning
(`snapshot_cron_*`, default 11:00 America/New_York — before the 1 pm kickoffs)
job that assembles the current week and calls `save_snapshot`. Because the
write is `ON CONFLICT DO NOTHING` the job is safe to miss, re-fire, or race with
the manual `POST /api/history/capture`; the first write for a `(season, week)`
wins and every later one is a no-op. Capture failures are logged, never
alerted — a missed snapshot is recoverable next tick, and the manual endpoint
is always available.

### 5. Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /api/history` | every snapshot for the season, newest week first, each with its `captured` payload and its `outcome` (null until backfilled). `pending` is now `false`. |
| `GET /api/history/{week}` | one week's record for the configured season, `404` if no snapshot for it. Prior seasons are retained in the table but not reachable per-week in v1 (the tool models one active season). |
| `POST /api/history/capture` | capture the current assembled week (`?week=` to pin one); returns the record, `created: false` when one already existed. |
| `POST /api/history/{week}/outcome` | backfill the actual outcome; `404` if no snapshot, `409` if already backfilled. |

`HistoryResponse.snapshots` is retyped from `list[dict]` to
`list[HistoryRecordOut]` and `pending` flips to `false`. ADR-0013 §5's
additive-only rule is knowingly broken once here: the field was a placeholder
shipped empty with `pending: true` explicitly "until issue #17", no frontend
consumes it yet (#19 is blocked on this ticket), and this ADR is that change's
record.

## Why

- **Persist the contract, not a new shape.** The four response models already
  are "projections, lineups, recommendations, and strategic outputs"; a
  parallel snapshot schema would be a second source of truth to migrate every
  time a screen gains a field.
- **Two tables over nullable columns.** The ticket's hard requirement is that
  original fields are never mutated. A separate append-only outcome table makes
  that impossible to get wrong, and keeps the "unscored week" query trivial.
- **`ON CONFLICT DO NOTHING` over a check-then-insert.** The immutability
  guarantee holds even if the cron and a manual capture race, with no lock and
  no read-modify-write.
- **Body-supplied actuals in v1.** The nflverse path needs a post-MNF pull to
  have landed and a resolver from snapshot player ids back to nflverse ids;
  that is real work with its own correctness surface, and `build_outcome`
  staying pure means adding it later is additive.

## Consequences

- `snapshot/` is a new package: `models.py` (frozen dataclasses), `store.py`
  (the two tables, `ensure_snapshot_tables` lazily like `ingest/status.py`),
  `backfill.py` (pure `build_outcome`). It imports nothing from `api/`.
- `api/serialize.py` now owns the four serializers; `api/weekly.py` and
  `api/layers.py` import them instead of inlining. `api/history.py` is the new
  router and also carries `capture_week` and `register_weekly_snapshot_capture`
  (the cron), the same way `api/ops.py` pairs with `api/refresh_runner.py`.
  `api/ops.py` loses the placeholder `history` handler.
- The season-history approximation in `assemble_week` (ADR-0013 §4) is **not**
  deleted here — wiring `prior_team_weeks` from stored snapshots is its own
  follow-up. This ticket lands the record it will read.
- `db.py::SCHEMA_VERSION` is unchanged; the snapshot tables are ensured lazily
  by `store.py`, the established per-feature pattern.

## Considered alternatives

- **One table with nullable `actual_*` columns, `UPDATE` to backfill.**
  Rejected: the ticket's immutability requirement then rests on no one writing
  an `UPDATE`, and the immutability test can only check behaviour, not
  structure.
- **Persist a bespoke minimal snapshot shape.** Rejected: the History screen
  wants the same projection/lineup/strategic detail the live screens show;
  a smaller shape just gets grown back to the contract, field by field.
- **Capture lazily on the first `GET /api/weekly` of a new week.** Rejected: a
  read endpoint that writes is surprising, and the snapshot would freeze
  whenever the week's first page view happened to land rather than at a defined
  pre-kickoff moment.
- **Compute the outcome from nflverse in this ticket.** Rejected as scope: it
  needs the post-games pull and an id resolver; the pure `build_outcome` seam
  keeps it a clean follow-up.
