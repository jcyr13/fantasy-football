# VPS deployment: one `docker compose up`, reachable only over Tailscale, Cloudflare Tunnel as the fallback

Issue #20 asks for the full stack deployed to the Hostinger VPS as a single
`docker compose up`, reachable from John's phone but **not on the public
internet**, with the nflverse weekly cron and the consensus sidecar running on
the VPS and a clean recovery after a restart. Issue #1's implementation notes
already fix the shape: two deployables coordinated by Compose, deployed to the
Hostinger VPS "reachable over Tailscale (Cloudflare Tunnel is the fallback)".

This ADR records *how* the existing images (`docs/adr/0003`, `docs/adr/0005`)
become that deployment without new application code.

## Decision

### 1. One `docker-compose.yml`, production-first, still fine for local dev

No `docker-compose.prod.yml` overlay. The base file gains what production needs
and what local dev tolerates:

- **`restart: unless-stopped`** on `api` and `web`. With the Docker daemon
  enabled at boot (`systemctl enable docker`) this is the whole of "a restart
  brings all services back cleanly" — the containers come back on reboot, and
  `api`'s APScheduler starts its crons in its lifespan.
- **Healthchecks** on `api` (`GET /api/health` via `python -m urllib`) and `web`
  (busybox `wget` on `/`). `web` waits on `api` being `service_healthy`, so a
  cold `up` orders itself.
- **Bind address variables.** Ports publish on `${WEB_BIND:-127.0.0.1}` /
  `${API_BIND:-127.0.0.1}`. The default is loopback-only, so an un-configured
  `docker compose up` — on a laptop or the VPS — is never exposed. Production
  sets `WEB_BIND` to the host's **Tailscale IP** (`tailscale ip -4`); `API_BIND`
  stays on loopback because only `web` talks to the API, over the compose
  network.
- **`api` env passthrough** for the SMTP settings behind the nflverse failure
  alert (user story #42) and `TZ`, all with the config defaults so a missing
  `.env` changes nothing.

`.env` (gitignored) carries the per-host values; `.env.example` is the committed
template. `docker compose` loads `.env` automatically for `${VAR}`
substitution.

### 2. Access layer: Tailscale primary, Cloudflare Tunnel fallback

**Tailscale** is the access path. `tailscale up` on the VPS puts it on John's
tailnet; `WEB_BIND` = its `100.x` address means the published port exists only
on the `tailscale0` interface. `ufw` is the second layer: allow OpenSSH, allow
`in on tailscale0`, default-deny inbound — so even a misconfigured `WEB_BIND`
is not reachable from the public interface. John's phone runs the Tailscale app
and opens `http://<vps-hostname>:8080` over MagicDNS.

**Cloudflare Tunnel** is the documented fallback, wired as a profile-gated
`cloudflared` service (`profiles: ["cloudflare"]`, so `docker compose up` never
starts it). `docker compose --profile cloudflare up -d` runs the connector with
a `TUNNEL_TOKEN`; the tunnel routes a public hostname to `http://web:80` over
the compose network. Because that hostname *is* public, it is paired with a
**Cloudflare Access** policy (email OTP to John's address) — the tunnel is the
transport, Access is the "restricted to me". Used when Tailscale is down or
blocked (a captive portal, a locked-down network).

### 3. The two weekly jobs on the VPS

- **nflverse weekly refresh** and the **consensus re-score** run inside the
  always-on `api` container. Their `CronTrigger`s pin
  `America/New_York` explicitly (`ingest/schedule.py`,
  `consensus/schedule.py`), so they are correct regardless of the host clock.
  `misfire_grace_time=3600` covers a short restart across the fire time; a
  longer outage is recovered with `docker compose exec api python -m
  deadparrots.ingest`.
- **The `ffanalytics` consensus sidecar** is a one-shot (`docs/adr/0005`). The
  systemd units already in `rsidecar/deploy/consensus-feed.{service,timer}` run
  `docker compose run --rm rsidecar` on Wednesday 05:30 ET, ahead of the api's
  06:00 re-score. `deploy/README.md` is where they get installed as part of
  standing the box up; this ADR does not add new units.

## Why

- **One compose file over an overlay.** The differences that matter (restart,
  healthchecks, bind address) are either harmless locally or driven by `.env`.
  An overlay would be a second file to keep in step for no behavioural gain, and
  `ports` entries can't be *removed* by an overlay anyway.
- **Loopback default.** "Not on the public internet" should be true before
  anyone reads the runbook, not because they followed it. The tailnet IP is
  opt-in via `.env`.
- **Tailscale over a reverse proxy + auth.** No public certificate, no login
  page to write and harden, no fail2ban. The device is the credential. This is
  a single-user tool.
- **Access, not just a Tunnel, for the fallback.** A bare Cloudflare Tunnel
  publishes the dashboard to the world. The ticket's "restricted to me" holds
  only with an Access policy in front.
- **Reuse the rsidecar units.** #8 already shipped and documented them; this
  ticket points at them rather than forking a second copy.

## Considered alternatives

- **`docker-compose.prod.yml` overlay.** Rejected — see Why. Kept as an option
  if prod ever needs a service local dev must not run; the `cloudflared` profile
  covers today's version of that need.
- **Publish on `0.0.0.0` and rely on `ufw` alone.** Rejected: one `ufw disable`
  during debugging and the dashboard is public. Binding to the tailnet IP means
  the socket isn't there to reach.
- **Tailscale Serve / Funnel instead of publishing a port.** Viable and tidy
  (TLS, no `WEB_BIND`), but Funnel *is* public exposure and Serve adds a moving
  part in front of `web`. Publishing on the tailnet IP is the smaller change;
  Serve can replace it later without touching the images.
- **`cloudflared` always-on as the only access path.** Rejected: it makes the
  dashboard's reachability depend on a public edge and an Access login for the
  everyday case, when the everyday case is John's own devices on the tailnet.
- **A host cron for the nflverse pull.** Rejected: the `api` already hosts
  APScheduler with misfire handling and one timezone story; a host cron would be
  a second scheduler to reason about.
- **Run `cloudflared` outside compose (host service).** Works, but then tunnel
  setup is a separate runbook; a profile keeps it one `--profile cloudflare`
  away.

## Consequences

- New files: `.env.example` (committed template), `deploy/README.md` (the VPS
  runbook), `deploy/preflight.sh` (pre-bring-up checks). `docker-compose.yml`
  gains the `cloudflared` service and the hardening above.
- The VPS needs a one-time prep: Docker Engine + Compose plugin, `docker`
  enabled at boot, Tailscale, `ufw`, the VPS timezone set to
  `America/New_York`, the rsidecar systemd timer installed. All in
  `deploy/README.md`.
- Local `docker compose up --build` is unchanged for the documented flow —
  `web` on `localhost:8080`, `api` on `localhost:8000`. Only cross-machine LAN
  access to a dev stack is lost (nobody relied on it).
- `test_deployment_compose.py` guards the ACs structurally: restart policies and
  healthchecks on the long-running services, the bind-address variables (no
  hardcoded `0.0.0.0` publish), and the `sidecar` / `cloudflare` profile gates.
- Reversing to a public deployment means dropping the bind variables and adding
  a real TLS + auth front end — a deliberate change, not a config slip.
