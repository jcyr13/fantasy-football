# Dead Parrots Dashboard

_RIP TIDE Fantasy Football Management Dashboard._

A single-user decision-support dashboard for managing the **Dead Parrots** team
in the **RIP TIDE League** (Yahoo, 12-team head-to-head). It produces
recommendations only; it never executes a roster move.

See `CONTEXT.md` for domain vocabulary, `docs/adr/` for architecture decisions,
`PRD.md` for the original requirements, and GitHub issue #1 for the v1 spec.

## How it ships

The dashboard is a **desktop app** that runs on the owner's own computer
(`docs/adr/0016`). An Electron shell launches the FastAPI backend as a local
child process, serves the built SPA, and stores data in a per-user app-data
directory. A signed-in **embedded browser view** does the one-click Yahoo
assisted pull. There is no server and no phone access; the scheduled jobs run
while the app is open and **catch up on the next launch** when a window was
missed.

> The previous VPS + Tailscale + Cloudflare deployment (`docs/adr/0015`) is
> **retired**. Its runbook survives as the "old VPS deployment" appendix in
> `deploy/README.md` for history only.

## Layout

| Path         | What                                                                    |
| ------------ | ---------------------------------------------------------------------- |
| `backend/`   | FastAPI service — all ingestion, scoring, projection, simulation logic |
| `frontend/`  | React + Vite + TypeScript SPA — presentation and interaction only     |
| `rsidecar/`  | Standalone R image for the `ffanalytics` consensus feed               |
| `data/`      | Local parquet cache, SQLite app DB, snapshots — gitignored            |
| `docs/`      | ADRs, methodology, agent guides                                       |

## Run it for development

Two processes, the same way the desktop shell launches them:

```sh
# backend — http://localhost:8000
cd backend && uv sync && uv run uvicorn deadparrots.app:app --reload

# frontend — http://localhost:5173 (proxies /api to :8000)
cd frontend && npm install && npm run dev
```

`GET /api/health` reports the SQLite app DB, the DuckDB connection, and the
APScheduler instance. Data lives under `./data/` by default
(`DEADPARROTS_DATA_DIR` to move it). Copy `.env.example` to `.env` only if you
want to override a default.

Seed the data the schedulers would otherwise wait days for:

```sh
cd backend
uv run python -m deadparrots.ingest                       # nflverse now
uv run python -m deadparrots.consensus --week <current>   # consensus now
uv run python -m deadparrots.yahoo --replay <pull_id>     # re-normalize an archived Yahoo pull
```

The live Yahoo assisted pull needs the desktop shell's signed-in browser view
(`docs/adr/0016 §3`); until that ships, develop the Yahoo-fed layers with
`--replay` against an archived pull.

## More

- `backend/README.md`, `frontend/README.md` — per-service dev notes
- `rsidecar/README.md` — the consensus-feed R image
- `deploy/README.md` — packaging the desktop installer, plus the retired VPS runbook
