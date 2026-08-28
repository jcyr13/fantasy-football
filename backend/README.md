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
