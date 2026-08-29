# backend

FastAPI service that owns all ingestion, scoring, projection, simulation,
strategic-layer, and snapshot logic for the Dead Parrots Dashboard
(see `../CONTEXT.md` and `../docs/adr/0003-python-for-numeric-logic-react-presentation-only.md`).

## Develop

```sh
uv sync
uv run uvicorn deadparrots.app:app --reload   # http://localhost:8000
uv run pytest
uv run ruff check
```

`GET /api/health` reports whether the SQLite app DB, the DuckDB connection, and
the APScheduler instance came up. Data lives under `../data/` by default;
override with `DEADPARROTS_DATA_DIR`.

## nflverse ingestion

```sh
uv run python -m deadparrots.ingest        # pull all nflverse datasets now
```

Pulls play-by-play, weekly player stats, rosters, schedules, snap counts, depth
charts, injuries, and the individual-defender table via `nflreadpy` into
timestamped parquet under `../data/nflverse/` (see
`../docs/adr/0004-nflverse-parquet-cache-layout.md`). Each run records a row per
dataset in `nflverse_pull_status` (SQLite) and, on any failure, emails John
(needs `DEADPARROTS_SMTP_HOST` etc.; logs at ERROR otherwise). The running API
also runs this on a weekly cron (`DEADPARROTS_NFLVERSE_CRON_*`).

## Consensus feed

```sh
uv run python -m deadparrots.consensus --week 1            # auto: rsidecar drop, else Sleeper
uv run python -m deadparrots.consensus --week 1 --source sleeper
uv run python -m deadparrots.consensus --replay <pull_id>  # re-normalize an archived payload
```

Fetches one week of external consensus projections, archives the raw payload
under `../data/consensus/<pull_id>/`, and **re-scores it to RIP TIDE rules
through the scoring engine** — `ffanalytics` (run in the one-shot `../rsidecar/`
and dropped into `../data/consensus/rsidecar/`) or, as the Week-1 stopgap and
automatic fallback, the Sleeper public API (see
`../docs/adr/0005-consensus-feed-rescored-by-the-engine.md`). Each run records a
`consensus_pull_status` row; a failure is logged, not emailed (a stale
cross-check degrades the model rather than breaking it). The running API runs
this weekly (`DEADPARROTS_CONSENSUS_CRON_*`, `DEADPARROTS_CONSENSUS_SOURCE`).
