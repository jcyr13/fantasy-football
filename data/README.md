# data/

Local, gitignored working data. Nothing here is committed.

- `app.sqlite` — application state: weekly snapshots, saved scenarios, notes,
  source-pull status, the later encrypted Yahoo token.
- `analytics.duckdb` — DuckDB database for analytical queries.
- Raw source pulls (nflverse parquet, Yahoo payloads, news) land here in later
  tickets, retained as timestamped files.

The directory is created and populated on first backend startup. Override its
location with `DEADPARROTS_DATA_DIR`.
