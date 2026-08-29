# nflverse ingestion: append-only timestamped parquet cache

The nflverse datasets the model needs (`pbp`, `player_stats`, `rosters`, `schedules`, `snap_counts`, `depth_charts`, `injuries`, and the individual-defender table) are pulled via `nflreadpy` and cached to disk. Every recommendation must be reproducible from the exact source snapshot it used (spec user story #63), so the cache is **append-only**: each pull writes a new set under `data/nflverse/<pull-id>/<dataset>.parquet`, where `<pull-id>` is the run's UTC start time (`YYYYMMDDTHHMMSSZ`, lexically sortable). Nothing is ever overwritten — a second write to the same path raises. DuckDB reads the parquet directly (`nflverse_<dataset>` views over the latest pull), so cached data is queryable with no load step.

## Considered Options

- **Overwrite a single `latest/` set per dataset** — rejected: destroys the ability to reproduce an older week's numbers.
- **One parquet file per dataset with an appended `pulled_at` column** — rejected: rewrites a growing file every week (churn, corruption risk) and couples all pulls into one artifact.
- **A new timestamped directory per pull, retained indefinitely** — chosen. Cheap, immutable, trivially diffable, and a whole pull is one `rm -rf` if ever needed.

## The IDP table

`nflreadpy.load_player_stats(summary_level="week")` already carries the individual-defender columns (`def_tackles_solo`, `def_tackle_assists`, `def_tackles_for_loss`, `def_pass_defended`, `def_sacks`, `def_interceptions`, forced fumbles, fumble recoveries, blocks, safeties). The `idp` dataset is therefore that same payload **projected to its identity + `def_*` / `fumble_recovery_*` columns** during normalization, not a separate download. If nflverse later splits defensive stats into their own resource, only the `idp` `DatasetSpec` changes.

## Consequences

- Disk grows ~15 MB per weekly pull (dominated by `pbp`); acceptable for a single-season, single-user tool. Retention/pruning is a later concern, not v1.
- The fetch boundary (`LiveNflverseSource`) is the one place that imports `nflreadpy`; everything downstream works against recorded parquet/polars fixtures. Ingestion normalization is tested recorded-payload-in → normalized-dataset-out.
- Only nflverse auto-refreshes (weekly APScheduler cron); a failed pull emails John (falls back to an ERROR log when SMTP is unconfigured). This does not change ADR-0001's stance that Yahoo stays a manual assisted pull.
