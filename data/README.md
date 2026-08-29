# data/

Local, gitignored working data. Nothing here is committed.

- `app.sqlite` — application state: weekly snapshots, saved scenarios, notes,
  source-pull status (incl. `nflverse_pull_status`), the later encrypted Yahoo
  token.
- `analytics.duckdb` — DuckDB database for analytical queries. On startup it
  gets an `nflverse_<dataset>` view over the latest cached parquet for each
  nflverse dataset.
- `nflverse/<pull-id>/<dataset>.parquet` — raw nflverse pulls (`pbp`,
  `player_stats`, `rosters`, `schedules`, `snap_counts`, `depth_charts`,
  `injuries`, `idp`). Each pull is a new UTC-timestamped set
  (`YYYYMMDDTHHMMSSZ`); existing sets are never overwritten. Retained
  indefinitely. Written by the weekly APScheduler job or
  `python -m deadparrots.ingest`.
- Yahoo payloads and news land here in later tickets, also as timestamped files.

The directory is created and populated on first backend startup. Override its
location with `DEADPARROTS_DATA_DIR`.
