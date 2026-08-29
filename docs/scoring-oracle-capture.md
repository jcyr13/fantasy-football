# Capturing the 2025 Yahoo scoring oracle

The RIP TIDE scoring engine (`deadparrots.scoring`) is a pure function and is
**not trusted** until it reproduces real 2025 Yahoo per-player weekly fantasy
points *exactly* for every offense / kicker / team-DEF player-week (spec issue
\#1, "Validation gate (hard)"). That comparison lives in
`backend/tests/test_scoring_gate.py` and it **skips** until two golden-fixture
files exist:

| File | What it holds | Produced by |
| --- | --- | --- |
| `backend/tests/fixtures/scoring/yahoo_2025_oracle.json` | Yahoo's own weekly fantasy-point total per scoring entity | `yfpy`, step 2 below |
| `backend/tests/fixtures/scoring/nflverse_2025_stat_rows.json` | the counting-stat rows the engine scores | the parquet cache, step 3 below |

This is a **one-off manual capture**. It needs a Yahoo account in the RIP TIDE
League (ID `735806`) and a Yahoo developer app; it cannot run in CI.

---

## Step 0 — one-time Yahoo app credentials

1. Create an app at <https://developer.yahoo.com/apps/create/> — OAuth 2.0,
   read-only Fantasy Sports scope (`fspt-r`). Redirect URI can be
   `https://localhost:8080`.
2. Note the **Client ID (consumer key)** and **Client secret**.
3. Install the capture-only dependency (kept out of `pyproject.toml` so CI never
   pulls it):

   ```bash
   cd backend
   uv pip install yfpy
   ```

## Step 1 — authenticate

From `backend/`, with the credentials in the environment:

```bash
export YAHOO_CONSUMER_KEY=...      # PowerShell: $env:YAHOO_CONSUMER_KEY = "..."
export YAHOO_CONSUMER_SECRET=...
```

The first `yfpy` call opens a browser consent page and caches an OAuth token
next to `--auth-dir` (default: the current directory). Keep that token file out
of git — `data/` or a scratch dir is a good home for it.

## Step 2 — capture the oracle

```bash
cd backend
uv run python -m deadparrots.scoring.oracle \
    --season 2025 \
    --auth-dir ../data \
    --out tests/fixtures/scoring/yahoo_2025_oracle.json
```

This walks every team's weekly roster for weeks 1–17 and records each rostered
player's `player_points.total`. Rows are tagged:

- `offense` — Yahoo position QB / RB / WR / TE, keyed by Yahoo `player_id`
- `kicker` — Yahoo position K, keyed by Yahoo `player_id`
- `team_defense` — Yahoo position DEF, keyed by the team abbreviation (e.g. `BUF`)
- IDP ("D" slot) players are **skipped** — that surface is a separate ticket.

The script prints a per-unit count when it finishes.

## Step 3 — build the matching stat rows

The engine scores `nflverse_2025_stat_rows.json`, so every oracle key must have
a stat row under the **same** `entity_id`. Because the oracle is keyed by Yahoo
`player_id` and nflverse is keyed by its own `player_id`, the stat-row builder
must join through `nflverse_rosters.yahoo_id`:

1. Make sure the 2025 nflverse pull is in the cache (ticket #3):

   ```bash
   DEADPARROTS_NFLVERSE_SEASONS='[2025]' uv run python -m deadparrots.ingest
   ```

2. Build the rows from the parquet cache (offense + kicker straight from
   `nflverse_player_stats` via `deadparrots.scoring.adapters`; team defense
   rolled up from `nflverse_pbp` — sacks/INTs/fumble recoveries/defensive TDs/
   safeties/blocked kicks/TFL by `defteam`, and points allowed from the
   schedule). Write the result with
   `deadparrots.scoring.oracle.write_stat_rows_fixture(...)`.

   Team-defense roll-up from play-by-play is the part most likely to need
   iteration against real column names; a first capture may legitimately land
   `offense` + `kicker` only and add `team_defense` in a follow-up — the gate
   checks whatever units are present and fails only on a mismatch.

## Step 4 — run the gate

```bash
cd backend
uv run pytest -m gate -v
```

- **Skips** — a fixture file is still missing.
- **Passes** — every offense/kicker/DEF player-week matches Yahoo to `0.00`.
- **Fails** — the output lists each mismatch as
  `unit name wkN: engine ±X.XX vs Yahoo ±Y.YY (delta ±Z.ZZ)` plus any oracle
  keys with no stat row.

## Interpreting a failure

A systematic offset across many players points at a **ruleset** gap, not an
engine bug — fix it in `deadparrots.scoring.ruleset.RIP_TIDE_RULESET` and re-run.
Known candidates:

- **Offensive fumble lost.** The PRD scoring list does not mention one, so
  `OffenseRules.fumble_lost` defaults to `0.0`. If kept players with lost
  fumbles read exactly `2 * fumbles` low, set it to `-2.0`.
- **Field-goal band edges / missed-FG rules** beyond the 0–19 penalty.
- **Points-allowed** definition for team defense (does Yahoo include
  defensive/special-teams TDs the offense allowed, pick-sixes, etc.).

A one-off per-player discrepancy that does not generalise is an NFL
gamebook-vs-Yahoo scorer difference; catalogue it in the PR that lands the
fixtures, don't bend the ruleset to it.

## Refreshing

The fixtures are frozen golden data — regenerate only if Yahoo restates 2025
scoring or the league's settings are corrected. Re-run steps 2–4 and commit the
new files with a note on what changed.
