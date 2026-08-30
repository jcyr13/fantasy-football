# desktop

The Electron shell that runs the Dead Parrots Dashboard as a desktop app
(`../docs/adr/0016`). It launches the existing FastAPI backend as a child
process on a private loopback port, serves the already-built SPA, and points the
backend's data directory at a per-user app-data folder.

This is **Job 1** of issue #43 — the shell boots the Dashboard. The embedded
Yahoo browser (#45), the "Pull from Yahoo" control (#46) and the Windows
installer (#47) come later. Nothing here bundles Python; dev uses the repo's
`uv`.

## Prerequisites

- **Node 20+** and npm (for Electron).
- **`uv`** on your `PATH` — the shell runs the backend with
  `uv run uvicorn deadparrots.app:app`, exactly as `backend/README.md` does. If
  `uv` is installed somewhere not on Electron's `PATH`, set `DEADPARROTS_UV_BIN`
  to its full path.
- The backend's own deps synced once: `cd ../backend && uv sync`.
- **A built SPA at `../frontend/dist`** (see below).

## Build the SPA

The shell loads `../frontend/dist`; it does not build it. Produce it with the
frontend's normal build:

```sh
npm --prefix ../frontend install
npm --prefix ../frontend run build
```

Re-run that whenever the frontend changes. `frontend/dist` is gitignored, so a
fresh checkout always needs this step.

## Run

```sh
npm install      # first time, pulls Electron
npm start
```

`npm start` opens one window rendering the live Dashboard. On launch the shell:

1. picks a free port and starts the backend bound to `127.0.0.1` on it;
2. registers the `app://` scheme, which serves the SPA from `../frontend/dist`
   and proxies `/api/*` to the backend so the SPA's hard-coded `/api` base works
   with no change;
3. waits for `GET /api/health` to pass, then shows the window;
4. on window close / quit, terminates the backend child (and its whole process
   tree — no orphan `uvicorn`).

Because the machine is normally off overnight, the backend's **on-launch
catch-up sweep** (`DEADPARROTS_CATCHUP_ON_LAUNCH`, on by default; shipped in
PR #42) re-fires any scheduled pull whose window passed while the app was
closed. The shell relies on that default — it sets nothing.

Data — the parquet cache, SQLite app DB, DuckDB file, archived pulls, weekly
snapshots — is written under the Electron per-user app-data directory
(`app.getPath('userData')/data`), **not** the repo. On Windows that is
`%APPDATA%\Dead Parrots Dashboard\data`. A second launch reuses it.

The backend is unchanged and still runs standalone:

```sh
cd ../backend && uv run uvicorn deadparrots.app:app
```

## Environment overrides

| Variable                | Effect                                                      |
| ----------------------- | --------------------------------------------------------- |
| `DEADPARROTS_UV_BIN`    | Full path to the `uv` executable if it is not on `PATH`.  |

## Tests

```sh
npm test      # node --test, no Electron runtime needed
```

The suite covers the pure pieces of the shell: free-port selection, the
`app://` request handler (static files + `/api` proxy, gzip pass-through, 404 /
502 paths), the backend command builder and health poll, MIME mapping, path
resolution and the "SPA not built" guard. The Electron window itself is verified
by hand against the acceptance criteria in issue #44.
