# Ship as a desktop app (Electron) with an embedded signed-in Yahoo browser; retire the VPS deployment

Issue #41 makes two calls the owner has already committed to:

1. Finish the "one-click assisted pull" that #7 scaffolded but never wired to a
   real Yahoo session, by running the scrape inside a **real embedded browser
   view** the owner has signed into.
2. **Retire the VPS + Tailscale + Cloudflare deployment** (issue #20,
   ADR-0015). The dashboard runs on the owner's own computer.

This ADR records the shape. It **supersedes ADR-0015**.

## Decision

### 1. An Electron shell wrapping the existing backend and SPA

The dashboard becomes a desktop application. The Electron **main process**:

- spawns the existing FastAPI backend as a local child process
  (`uvicorn deadparrots.app:app`), bound to `127.0.0.1` on a free port;
- loads the already-built SPA (`frontend/dist`) in the main `BrowserWindow`,
  pointed at that backend;
- stores all data in a per-user app-data directory
  (`app.getPath('userData')/data`), passed to the backend as
  `DEADPARROTS_DATA_DIR`. This replaces the compose bind mount.

No application code in `backend/` or `frontend/` changes shape for this — the
shell is new code under a new top-level directory. The backend stays a normal
FastAPI app that also runs under `uvicorn` for development.

**Electron, not Tauri.** Electron's `BrowserWindow` / `webContents` give
first-class webview scripting — `executeJavaScript`, `session` partitions,
per-window persisted cookies — which is exactly what the assisted pull needs.
Tauri's smaller footprint is attractive but its webview automation is more
limited and would be a spike-and-hope; the scrape is the whole point of moving
to a desktop app, so it gets the low-risk option.

### 2. An embedded, persistently signed-in Yahoo browser view

A second `BrowserWindow` (or `BrowserView`) on a **named `session`
partition** (`persist:yahoo`) is the Yahoo browser. The owner signs in once;
cookies persist in the partition between launches. Re-authentication is only
needed when Yahoo expires the session, and the "Pull from Yahoo" flow detects
that and reopens this window.

### 3. `PageExtractor` over a loopback HTTP seam

The backend already defines the assisted pull behind a `YahooSource` /
`PageExtractor` interface (ADR-0001, issue #7). The desktop shell implements
the extractor **in the main process** and exposes it to the backend as a small
loopback HTTP endpoint:

```
POST http://127.0.0.1:<port>/scrape   {"page": "matchup", "url": "https://…"}
  -> 200  { …the page payload in the shape `normalize` expects… }
```

For each of the four pages the main process loads the URL in the Yahoo window,
waits for it to settle, and **executes JavaScript in the webview** to read the
page — the embedded `__PRELOADED_STATE__` / Fantasy bootstrap JSON where Yahoo
exposes one, falling back to reading the rendered DOM — and returns that payload
as JSON. It does not intercept Yahoo's private XHR endpoints; the DOM / embedded
blob is what the recorded fixtures (`backend/tests/fixtures/yahoo/*.json`) are
shaped like, so the normalizers and the tested contract do not move.

The backend half is `BrowserYahooSource(HttpPageExtractor(url))`, wired into
`app.state.yahoo_source` by `build_yahoo_source(settings)` when
`DEADPARROTS_YAHOO_EXTRACTOR_URL` is set. A bare backend with no shell leaves it
unset and `POST /api/yahoo/pull` answers 503 exactly as before.

### 4. Catch-up scheduling on launch

The APScheduler crons (nflverse refresh, consensus re-score, news poll, Sunday
snapshot capture) only tick while the app is open, and the owner's computer is
off overnight. Two mechanisms cover the gap:

- **Misfire grace** on the three weekly cron jobs (nflverse refresh, consensus
  re-score, Sunday snapshot) goes from 1 hour to **6 hours**
  (`scheduler.RECURRING_JOB_MISFIRE_GRACE_SECONDS`), covering a normal
  overnight close. The news poll keeps its 5-minute grace — a 30-minute
  interval job that the launch sweep re-fires on any cold start anyway.
- **A launch sweep** (`deadparrots.catchup`) runs on startup: for each job
  whose last **successful** run predates its most recent scheduled window, it
  bumps the job's `next_run_time` to now — reusing the exact callable the cron
  registered. The weekly **snapshot** is special-cased: if the current NFL
  week (per the latest Yahoo matchup pull) has **no snapshot** and its games
  are **final** (every kickoff date in that week is in the past, per the
  cached `nflverse_schedules` view), the capture is fired now, so an app
  closed all of Sunday still records that week on the History screen before
  Yahoo rolls the matchup page forward. Mid-week (games not final) is left to
  the normal Sunday cron. **Known limitation**: the "games final" check needs
  the nflverse schedule parquet to be cached; on a launch where it is not yet
  present the snapshot catch-up defers to a later launch (the nflverse refresh
  is itself part of the same sweep). A schedule-independent "week is over"
  signal is a follow-up. `DEADPARROTS_CATCHUP_ON_LAUNCH` turns the sweep off.

### 5. Packaging

An `electron-builder` NSIS installer for **Windows** (the owner's OS). The v1
build is **unsigned** — SmartScreen will warn on first run; the owner clicks
through. Code signing is a later nicety, not a blocker for a single-user tool.

### 6. Local development

`docker compose` is **removed**, not kept. Development runs the two processes
directly, the same way the shell launches them:

- backend: `uv run uvicorn deadparrots.app:app --reload`
- frontend: `npm run dev` (Vite proxies `/api` to the backend)
- desktop shell: `npm start` in the shell directory once it exists

`docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, and
`frontend/nginx.conf` are deleted. The `rsidecar/` image stays a standalone
`docker build` / `docker run` (its R + `ffanalytics` toolchain is genuinely
easier in a container); with the VPS gone its systemd timer is gone too, so on
the desktop the consensus feed normally rides the **Sleeper fallback** unless
the owner runs the sidecar by hand.

## Consequences

- **New**: a top-level desktop-shell directory (Electron main + preload +
  extractor), `electron-builder` config, the Windows installer artifact. Not
  built in CI.
- **Backend**: `Settings.yahoo_extractor_url` / `yahoo_extractor_timeout_seconds`
  / `catchup_on_launch`; `HttpPageExtractor` and `build_yahoo_source` in
  `deadparrots.yahoo.scrape`; `deadparrots.catchup`; the three weekly cron jobs
  share `RECURRING_JOB_MISFIRE_GRACE_SECONDS`. `app.py` wires both on startup.
- **Removed**: `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`,
  `frontend/nginx.conf`, `deploy/preflight.sh`, `.dockerignore`, the
  `test_deployment_compose.py` guard, and the `WEB_BIND` / `API_BIND` /
  `TUNNEL_TOKEN` / `TZ` knobs from `.env.example`.
- **Lost, accepted by the owner**: no access from a phone or other devices; the
  scheduled jobs only run while the app is open (mitigated by §4).
- **Docs**: `README.md`, `deploy/README.md`, `deploy/DEPLOY-FOR-BEGINNERS.md`
  are rewritten around the desktop app; the VPS / Tailscale / Cloudflare runbook
  is kept only as a clearly-marked historical appendix.
- **ADR-0015 is superseded** and marked as such; the #20 deployment work is
  obsolete.
- Issue #41 is large: the Electron shell, the embedded browser + live
  `PageExtractor`, and the packaged installer land in follow-up sub-issues. The
  backend seam (`build_yahoo_source`, `HttpPageExtractor`), the catch-up sweep,
  the misfire bump, this ADR, and the docs rewrite land first.

## Considered alternatives

- **Tauri.** Smaller, but webview automation is thinner and unproven for this
  scrape. Revisit only if Electron's bundle size becomes a real problem.
- **Intercepting Yahoo's XHR responses** instead of reading the DOM / embedded
  blob. Cleaner JSON, but couples the pull to Yahoo's private endpoints and
  drifts from the recorded fixture shapes the normalizers are tested against.
- **Keeping the VPS and adding a headless-browser scrape there.** Rejected by
  the owner: the phone access it bought is not worth the moving parts (a public
  edge, an Access policy, a tailnet, a second scheduler story) for a tool one
  person uses at a desk.
- **Keeping `docker compose` for local dev alongside the shell.** Rejected: a
  second run path to keep in step for no gain once the shell launches the
  processes directly.
- **A signed installer for v1.** Deferred: signing is cost and ceremony;
  clicking through SmartScreen once is acceptable for a single known user.
