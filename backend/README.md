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
