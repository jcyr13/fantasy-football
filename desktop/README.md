# desktop

The Electron shell that runs the Dead Parrots Dashboard as a desktop app
(`../docs/adr/0016`). It launches the existing FastAPI backend as a child
process on a private loopback port, serves the already-built SPA, and points the
backend's data directory at a per-user app-data folder.

Jobs **1** (#44 — shell boots the Dashboard) and **2** (#45 — embedded Yahoo
browser + live scrape endpoint) have landed. The "Pull from Yahoo" control (#46)
and the Windows installer (#47) come later. Nothing here bundles Python; dev uses
the repo's `uv`.

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

## The Yahoo assisted pull (Job 2, #45)

On launch the shell also:

1. creates a **hidden** `BrowserWindow` on the named `persist:yahoo` session
   partition — the embedded Yahoo browser. Its cookies live in the partition, so
   a sign-in survives between launches (`lib/yahoo-window.js`);
2. starts a loopback **`POST /scrape`** endpoint on another free `127.0.0.1`
   port (`lib/scrape-server.js`);
3. spawns the backend with `DEADPARROTS_YAHOO_EXTRACTOR_URL` pointed at it, so
   `build_yahoo_source(settings)` wires `BrowserYahooSource` into
   `app.state.yahoo_source` and `POST /api/yahoo/pull` runs a real pull instead
   of answering 503.

`POST /api/yahoo/pull` (or, until Job 3's button lands, `curl -XPOST
http://127.0.0.1:<backend-port>/api/yahoo/pull`) drives the Yahoo window through
the four pages — matchup, players, injuries, standings — reads each page's
payload out of the rendered DOM (the shape recorded in
`../backend/tests/fixtures/yahoo/*.json`), archives the raw payloads under
`<data_dir>/yahoo/<pull_id>/` with a `manifest.json`, and normalizes them.

**First run:** the first scrape lands on Yahoo's login page; the shell brings the
Yahoo window to the front so you can sign in once. Re-run the pull afterwards.

**Expired session:** a scrape that hits the login / consent gate returns
`401 Yahoo sign-in required` from `/scrape`. The backend records that page as a
failure whose error text carries the phrase — a clear signal, never a silent
success — and the shell re-raises the sign-in window. Job 3 (#46) turns that into
an in-app "sign in again" prompt.

**Bare backend:** run standalone without the shell and
`DEADPARROTS_YAHOO_EXTRACTOR_URL` is unset, so `POST /api/yahoo/pull` still
answers 503 — unchanged.

### Tuning the scrape against a live Yahoo session

`lib/yahoo-extract.js` holds the injected extraction script. Its selectors are
**header-text driven** (they key off column headings, not Yahoo's hashed class
names) but are a first cut — expect to tighten them against the real pages on the
first live pull. The script's failure return carries `via` / `reason` diagnostics
(which globals it saw, how many tables were on the page) to make that quick.
`DEAD_PARROTS_TEAM_NAME` there is the team flagged `is_dead_parrots` on the
matchup payload; change it if the team is renamed.

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
502 paths), the backend command builder / env / health poll, MIME mapping, path
resolution and the "SPA not built" guard, and — for Job 2 — the `/scrape` server
(payload pass-through, the 401 auth signal, 400/404/405/500/502 paths), the
Yahoo login-URL detector, the payload sanity check and the injected-script
builder. The Electron windows (main + the `persist:yahoo` Yahoo view) and the
live scrape against Yahoo are verified by hand against the acceptance criteria in
issues #44 and #45.
