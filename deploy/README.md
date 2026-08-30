# Delivering the Dead Parrots Dashboard

The dashboard ships as a **desktop app** that runs on the owner's computer
(`../docs/adr/0016`). This document covers packaging that app, and keeps the
**retired** VPS runbook as a historical appendix.

---

## Desktop app

### What runs where

| Piece | Where | Trigger |
| --- | --- | --- |
| FastAPI backend + APScheduler | local child process of the Electron shell | — |
| SPA | the shell's main window | — |
| nflverse refresh / consensus re-score / news poll / Sunday snapshot | inside the backend | APScheduler crons **+ catch-up on launch** |
| Yahoo assisted pull | the shell's embedded, signed-in browser view | the "Pull from Yahoo" control |
| `ffanalytics` consensus scrape | standalone `rsidecar` image, run by hand | none — Sleeper is the default fallback |

The crons pin `America/New_York` in code. Because the app is not always on, the
backend also runs a **catch-up sweep on startup** (`deadparrots.catchup`): any
job whose last successful run predates its most recent scheduled window is fired
immediately, and a finished NFL week with no weekly snapshot is captured so the
History screen never loses a week the app was closed for. Misfire grace on the
four jobs is 6 hours (`DEADPARROTS_CATCHUP_ON_LAUNCH=false` disables the sweep).

### Building the installer

`electron-builder` produces one **unsigned NSIS `.exe`** for Windows
(`../docs/adr/0016 §5`; issue #47). The backend ships **frozen** — a PyInstaller
`--onedir` bundle — so the target machine needs neither Python nor `uv` nor Node.

Build machine (Windows): **Node 20+**, **`uv`**, and the backend deps synced once
(`cd backend && uv sync`). Then, from the repo root:

```powershell
# 1. Build the SPA  ->  frontend/dist
npm --prefix frontend ci
npm --prefix frontend run build

# 2. Freeze the backend  ->  desktop/backend-dist/deadparrots-backend/
cd desktop
npm ci
npm run build:backend            # runs scripts/build-backend.ps1 (PyInstaller)

# 3. Build the installer  ->  desktop/dist/Dead Parrots Dashboard Setup <version>.exe
npm run dist                     # electron-builder --win nsis
```

`npm run dist` does **not** run steps 1–2 — the frozen backend and the built SPA
must already be in place; `electron-builder.yml` copies both in as
`extraResources` (`resources/backend/`, `resources/frontend/`). The shell then
picks the frozen `deadparrots-backend.exe` over `uv run uvicorn` by
`app.isPackaged` (`desktop/lib/paths.js`).

The `--collect-*` list in `scripts/build-backend.ps1` is a **first cut**: expect
to add hidden imports on the first real build (uvicorn's protocol/loop
autodetect, the `duckdb` native lib, `nflreadpy` → polars/pyarrow).
PyInstaller's `warn-deadparrots-backend.txt` under `desktop/backend-build/` lists
what it could not trace.

The installer is **unsigned** for v1 — Windows SmartScreen shows *"Windows
protected your PC"* on first run; click **More info → Run anyway**. Not built in
CI.

### First run

1. Install and launch. The backend child process comes up on a loopback port;
   data goes to the per-user app-data directory.
2. Open the embedded **Yahoo** window and sign in once. The session persists in
   a dedicated browser partition between launches.
3. Click **Pull from Yahoo**. All four pages scrape in one action; per-page
   success/failure is shown, and the Yahoo-fed screens populate.
4. Seed nflverse + consensus if the freshness header shows them as "never" —
   the catch-up sweep does this automatically on the next launch, or run
   `python -m deadparrots.ingest` / `deadparrots.consensus` in the checkout.

### Data & uninstall

All data lives in the per-user app-data dir —
`%APPDATA%\Dead Parrots Dashboard\data` — the SQLite app DB, the DuckDB file, the
parquet cache, archived Yahoo pulls, and weekly snapshots. The installer is
**assisted** (`oneClick: false` in `../desktop/electron-builder.yml`), and an
assisted NSIS uninstaller **leaves `%APPDATA%` in place** — so reinstalling or
upgrading keeps the History screen's snapshots. To wipe it, delete that folder by
hand after uninstalling.

### Running for development

See the root `README.md` — two processes (`uvicorn` + `npm run dev`), no
container.

### The consensus R sidecar

`ffanalytics` is easier to run in a container. With the VPS gone there is no
timer; run it by hand when you want a fresh drop, otherwise the backend falls
back to the Sleeper public API on its own. See `../rsidecar/README.md`.

---

## Appendix: old VPS deployment (retired)

> **Retired by `../docs/adr/0016` (issue #41).** The stack below is no longer
> deployed anywhere. Kept for history: how the dashboard ran on a Hostinger VPS
> as one `docker compose up -d`, reachable over Tailscale with Cloudflare Tunnel
> as a fallback, before it became a desktop app. `docker-compose.yml`, the
> Dockerfiles, `deploy/preflight.sh`, and the `WEB_BIND` / `API_BIND` /
> `TUNNEL_TOKEN` knobs it relied on have been removed from the repo. Decision
> record: `../docs/adr/0015-vps-deployment-over-tailscale.md`.

### 0. What ran where

| Piece | Where | Trigger |
| --- | --- | --- |
| `api` (FastAPI + APScheduler) | `api` container, always on | — |
| `web` (nginx + SPA) | `web` container, always on | — |
| nflverse weekly refresh | inside `api` | APScheduler cron, Tue 08:00 ET |
| consensus re-score | inside `api` | APScheduler cron, Wed 06:00 ET |
| news poll / Sunday snapshot capture | inside `api` | APScheduler |
| `ffanalytics` consensus scrape | `rsidecar` one-shot container | systemd timer, Wed 05:30 ET |
| Yahoo assisted pull | manual, from a signed-in browser | not on the VPS |

### 1. One-time VPS prep

Set the timezone (`sudo timedatectl set-timezone America/New_York`), install
Docker Engine + the Compose plugin (`curl -fsSL https://get.docker.com | sudo
sh`), `sudo systemctl enable --now docker` so a reboot brings the stack back,
and clone the repo to `/opt/fantasy-football` (the path the rsidecar systemd
unit expects).

### 2. Tailscale (primary access path)

`curl -fsSL https://tailscale.com/install.sh | sudo sh`, `sudo tailscale up
--ssh`, note `tailscale ip -4`. In the admin console: disable key expiry for the
node, keep MagicDNS on. On the phone: install Tailscale, stay signed in; the
dashboard was `http://<vps-hostname>:8080`.

Firewall — defence in depth:

```sh
sudo ufw allow OpenSSH
sudo ufw allow in on tailscale0
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
```

### 3. `.env`

`cp .env.example .env`, then set `WEB_BIND` to the `tailscale ip -4` address
(this is what kept the dashboard on the tailnet and nowhere else), leave
`API_BIND=127.0.0.1`, set `TZ=America/New_York`, optionally the
`DEADPARROTS_SMTP_*` App Password, and `TUNNEL_TOKEN` only for the Cloudflare
fallback.

### 4. Bring the stack up

```sh
cd /opt/fantasy-football
./deploy/preflight.sh
docker compose build
docker compose up -d
docker compose ps               # api + web -> "healthy" within ~30s
docker compose exec api python -m deadparrots.ingest
docker compose exec api python -m deadparrots.consensus --week <current-week>
```

### 5. Verify it is not public

From a device on the tailnet: `http://<vps-hostname>:8080` and
`.../api/health`. From off the tailnet: `curl --max-time 5
http://<vps-public-ip>:8080/` must hang or refuse.

### 6. Cloudflare Tunnel — the fallback access path

Used when Tailscale was unavailable (captive portal, restricted network). In the
Cloudflare Zero Trust dashboard: **Networks → Tunnels → Create a tunnel**
(`cloudflared`), copy the tunnel token, add a public hostname routing to
`web:80`. Put the token in `.env` as `TUNNEL_TOKEN`, then:

```sh
docker compose --profile cloudflare up -d
```

**Lock it down** with a Cloudflare **Access** policy (Zero Trust → Access →
Applications → Add → Self-hosted), one *Allow* rule on the owner's email
(one-time PIN). Without it the hostname was open to anyone with the URL.

### 7. The consensus sidecar timer

```sh
sudo cp rsidecar/deploy/consensus-feed.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now consensus-feed.timer   # Wed 05:30 ET
docker compose --profile sidecar build rsidecar
```

If no fresh drop existed on Wednesday, the api's re-score job fell back to the
Sleeper public API on its own.

### 8. Updating a deployed box

```sh
cd /opt/fantasy-football
git pull
./deploy/preflight.sh
docker compose build
docker compose up -d
docker compose --profile cloudflare up -d     # only if the fallback ran
```

`./data/` was a bind mount, so the SQLite DB, the DuckDB file, the parquet
cache, and the weekly snapshots survived rebuilds and `docker compose down`.

### 9. Restart & recovery

| Situation | What happened |
| --- | --- |
| VPS reboots | Docker started at boot; `api`/`web` were `restart: unless-stopped` and came back; APScheduler restarted its crons; the systemd timer re-armed. |
| A container crashed | Restarted automatically; `docker compose logs <svc>` for why. |
| Missed the Tue 08:00 nflverse window | `docker compose exec api python -m deadparrots.ingest`. |
| Locked out of Tailscale | Use the Cloudflare fallback, or Hostinger's web console to `sudo tailscale up` again. |
