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
- `rsidecar` → one-shot consensus scrape, only with `--profile sidecar`

Published ports bind to `127.0.0.1` by default (`WEB_BIND` / `API_BIND` in
`.env` — see `.env.example`), so nothing is exposed beyond the host until you
say so.

## Deploy to the VPS

The full stack runs on the Hostinger VPS as one `docker compose up -d`,
reachable over Tailscale and not the public internet, with Cloudflare Tunnel as
the fallback. Runbook: **`deploy/README.md`**. Decision record:
`docs/adr/0015-vps-deployment-over-tailscale.md`.

## Develop a service

See `backend/README.md` and `frontend/README.md`.
