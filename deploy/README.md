# Deploying the Dead Parrots Dashboard to the VPS

The whole stack runs on the Hostinger VPS as one `docker compose up -d`,
reachable from John's devices over **Tailscale** and not from the public
internet. **Cloudflare Tunnel** is the fallback access path. Decision record:
`../docs/adr/0015-vps-deployment-over-tailscale.md`.

Everything below is a one-time setup except [Bring the stack up](#4-bring-the-stack-up)
and [Updating](#8-updating-a-deployed-box), which you repeat.

---

## 0. What runs where

| Piece | Where | Trigger |
| --- | --- | --- |
| `api` (FastAPI + APScheduler) | `api` container, always on | — |
| `web` (nginx + SPA) | `web` container, always on | — |
| nflverse weekly refresh | inside `api` | APScheduler cron, Tue 08:00 ET |
| consensus re-score | inside `api` | APScheduler cron, Wed 06:00 ET |
| news poll / Sunday snapshot capture | inside `api` | APScheduler |
| `ffanalytics` consensus scrape | `rsidecar` one-shot container | systemd timer, Wed 05:30 ET |
| Yahoo assisted pull | **manual, from a signed-in browser** | not on the VPS |

The APScheduler crons pin `America/New_York` in code, so they are right no
matter the host clock. The rsidecar timer uses the system timezone — step 1
sets it.

---

## 1. One-time VPS prep

SSH in as a sudo user.

### Timezone

```sh
sudo timedatectl set-timezone America/New_York
```

### Docker Engine + Compose plugin

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"    # log out/in for this to take effect
sudo systemctl enable --now docker # <-- makes "a restart brings services back" work
docker compose version             # expect v2.x
```

### The checkout

```sh
sudo mkdir -p /opt/fantasy-football
sudo chown "$USER" /opt/fantasy-football
git clone https://github.com/jcyr13/fantasy-football /opt/fantasy-football
cd /opt/fantasy-football
```

The systemd unit in `rsidecar/deploy/` expects this exact path
(`/opt/fantasy-football`). Adjust `WorkingDirectory` if you clone elsewhere.

---

## 2. Tailscale (primary access path)

```sh
curl -fsSL https://tailscale.com/install.sh | sudo sh
sudo tailscale up --ssh          # opens an auth URL; approve it in your account
tailscale ip -4                  # note this 100.x.y.z address
```

In the Tailscale admin console:

- Confirm the VPS shows up and (optionally) **disable key expiry** for it so the
  tailnet connection does not drop after 180 days.
- Make sure **MagicDNS** is on, so devices can reach the box by hostname.

On John's **phone**: install the Tailscale app, sign in to the same account,
leave it connected. The dashboard will be `http://<vps-hostname>:8080`.

### Firewall — defence in depth

Binding to the tailnet IP (step 3) already keeps the port off the public
interface. `ufw` makes a `WEB_BIND` mistake harmless too:

```sh
sudo ufw allow OpenSSH
sudo ufw allow in on tailscale0
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
sudo ufw status verbose
```

If you use the Cloudflare fallback (step 6), outbound 443 is all it needs — no
inbound rule.

---

## 3. Configure `.env`

```sh
cp .env.example .env
```

Edit `.env`:

- **`WEB_BIND`** → the `tailscale ip -4` address from step 2. This is what makes
  the dashboard reachable over the tailnet and nowhere else.
- **`API_BIND`** → leave `127.0.0.1`.
- **`TZ`** → `America/New_York` (matches step 1).
- **`DEADPARROTS_SMTP_*`** → a Gmail App Password if you want the
  nflverse-failure email (user story #42). Leave blank to log the failure at
  ERROR instead.
- **`TUNNEL_TOKEN`** → only for the Cloudflare fallback (step 6).

`.env` is gitignored — it never leaves the box.

---

## 4. Bring the stack up

```sh
cd /opt/fantasy-football
./deploy/preflight.sh            # sanity-checks docker, .env, and the compose config
docker compose build
docker compose up -d
docker compose ps               # api + web should become "healthy" within ~30s
```

Seed the data the schedulers will otherwise wait days for:

```sh
docker compose exec api python -m deadparrots.ingest          # nflverse now
docker compose exec api python -m deadparrots.consensus --week <current-week>
```

The Yahoo assisted pull stays manual — run it from a signed-in browser as
usual; it is not part of the VPS stack.

---

## 5. Verify

From a device **on the tailnet** (John's phone, with Tailscale connected):

```
http://<vps-hostname>:8080         # dashboard
http://<vps-hostname>:8080/api/health   # {"status":"ok", ...}
```

Confirm it is **not** public — from a machine off the tailnet, or over cellular
with the Tailscale app disabled:

```sh
curl --max-time 5 http://<vps-public-ip>:8080/    # must hang / refuse
```

---

## 6. Cloudflare Tunnel — the fallback access path

Use this when Tailscale is unavailable (captive portal, restricted network).
The tunnel is the transport; a **Cloudflare Access** policy is what keeps the
public hostname restricted to John.

1. In the **Cloudflare Zero Trust** dashboard → **Networks → Tunnels →
   Create a tunnel** (type `cloudflared`). Name it, then copy the **tunnel
   token** from the "Install and run a connector" step.
2. Add a **Public hostname** on the tunnel: e.g.
   `parrots.example.com` → service `HTTP` → `web:80`.
3. Put the token in `.env`:
   ```sh
   TUNNEL_TOKEN=eyJ...        # the long token from step 1
   ```
4. Start the connector (profile-gated — a plain `docker compose up` never runs
   it):
   ```sh
   docker compose --profile cloudflare up -d
   docker compose logs -f cloudflared    # expect "Registered tunnel connection"
   ```
5. **Lock it down** — **Zero Trust → Access → Applications → Add → Self-hosted**,
   domain `parrots.example.com`, one policy: *Allow* when **email** is
   `johncyrboston@gmail.com` (one-time PIN). Without this the dashboard is open
   to anyone with the URL.

To stop the fallback: `docker compose --profile cloudflare down`. The rest of
the stack is unaffected.

---

## 7. The consensus sidecar timer

The `ffanalytics` scrape is a one-shot container run weekly from the host
(`../docs/adr/0005`). The units ship in `../rsidecar/deploy/`:

```sh
sudo cp rsidecar/deploy/consensus-feed.service /etc/systemd/system/
sudo cp rsidecar/deploy/consensus-feed.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now consensus-feed.timer
systemctl list-timers consensus-feed.timer      # next run: Wed 05:30 ET
```

Build the image once so the first fire is fast:

```sh
docker compose --profile sidecar build rsidecar
```

Test it end to end without waiting for Wednesday:

```sh
sudo systemctl start consensus-feed.service
docker compose run --rm rsidecar                # or run it directly
ls data/consensus/rsidecar/                     # a fresh <timestamp>.json
```

If no fresh drop exists on Wednesday, the api's re-score job falls back to the
Sleeper public API on its own — the sidecar failing degrades the cross-check,
it does not break the week.

---

## 8. Updating a deployed box

```sh
cd /opt/fantasy-football
git pull
./deploy/preflight.sh
docker compose build
docker compose up -d                 # recreates only what changed
docker compose --profile cloudflare up -d    # only if you run the fallback
```

`./data/` is a bind mount — the SQLite app DB, the DuckDB file, the parquet
cache, and the weekly snapshots survive rebuilds and `docker compose down`.

---

## 9. Restart & recovery

| Situation | What happens / what to do |
| --- | --- |
| VPS reboots | `docker` starts at boot; `api` and `web` are `restart: unless-stopped` and come back; APScheduler restarts its crons. The systemd timer re-arms. Nothing to do. The `web`-waits-for-`api`-healthy ordering only applies to `docker compose up`, not the boot path — after a cold reboot `web` may return 502 on `/api` for a few seconds until `api` passes its healthcheck, then self-heals. |
| A container crashes | Restarted automatically. `docker compose ps` shows restart counts; `docker compose logs <svc>` for why. |
| Full manual bounce | `docker compose down && docker compose up -d`. |
| Missed the Tue 08:00 nflverse window (long outage) | `docker compose exec api python -m deadparrots.ingest`. |
| `api` stuck "unhealthy" | `docker compose logs api`; check `./data/` is writable by the container (uid in the image) and not full. |
| Locked out of Tailscale | Use the Cloudflare fallback (step 6), or Hostinger's web console to `sudo tailscale up` again. |

---

## Troubleshooting

- **`preflight.sh` says the compose config is invalid** — run
  `docker compose config` to see the parse error. Usually a stray quote in
  `.env`.
- **Phone can't load the dashboard** — is the Tailscale app connected? Does
  `tailscale status` on the VPS list the phone? Is `WEB_BIND` in `.env` the
  current `tailscale ip -4` (it changes if you log the node out and back in)?
- **`web` healthy, dashboard 502s on `/api`** — `api` isn't healthy yet or
  crashed; `docker compose logs api`.
- **No nflverse email on failure** — `DEADPARROTS_SMTP_*` unset, or Gmail
  rejecting a non-App-Password. Check `docker compose logs api` for the ERROR
  line that replaces the email.
- **`cloudflared` won't register** — token wrong or missing; outbound 443
  blocked by `ufw` (it shouldn't be — `default allow outgoing`).
