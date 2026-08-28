# Dead Parrots Dashboard

_RIP TIDE Fantasy Football Management Dashboard._

A single-user decision-support dashboard for managing the **Dead Parrots** team
in the **RIP TIDE League** (Yahoo, 12-team head-to-head). It produces
recommendations only; it never executes a roster move.

See `CONTEXT.md` for domain vocabulary, `docs/adr/` for architecture decisions,
`PRD.md` for the original requirements, and GitHub issue #1 for the v1 spec.

## Layout

| Path         | What                                                                    |
| ------------ | ---------------------------------------------------------------------- |
| `backend/`   | FastAPI service — all ingestion, scoring, projection, simulation logic |
| `frontend/`  | React + Vite + TypeScript SPA — presentation and interaction only     |
| `rsidecar/`  | R sidecar for the `ffanalytics` consensus feed (stub until ticket #8) |
| `data/`      | Local parquet cache, SQLite app DB, snapshots — gitignored            |
| `docs/`      | ADRs, methodology, agent guides                                       |

## Run the whole stack

```sh
docker compose up --build
```

- `web`  → http://localhost:8080 (SPA; proxies `/api` to `api`)
- `api`  → http://localhost:8000 (FastAPI; `GET /api/health`)
- `rsidecar` → idles with a heartbeat until ticket #8

## Develop a service

See `backend/README.md` and `frontend/README.md`.
