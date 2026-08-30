#!/bin/sh
# Pre-bring-up sanity checks for a VPS deployment (docs/adr/0015, deploy/README.md).
# Run from the repo root:  ./deploy/preflight.sh
# Exits non-zero on anything that would make `docker compose up -d` wrong or unsafe.
set -eu

fail=0
warn=0
note() { printf '  %s\n' "$1"; }
err()  { printf 'FAIL  %s\n' "$1"; fail=1; }
wrn()  { printf 'WARN  %s\n' "$1"; warn=1; }
ok()   { printf 'ok    %s\n' "$1"; }

cd "$(dirname "$0")/.."

echo "== docker =="
if command -v docker >/dev/null 2>&1; then
  ok "docker present ($(docker --version | cut -d, -f1))"
else
  err "docker not on PATH — see deploy/README.md step 1"
fi

if docker compose version >/dev/null 2>&1; then
  ok "compose plugin present ($(docker compose version --short 2>/dev/null || echo v2))"
else
  err "'docker compose' not available (need the v2 plugin, not docker-compose v1)"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-enabled docker >/dev/null 2>&1; then
    ok "docker service enabled at boot (restart recovery works)"
  else
    wrn "docker service not enabled at boot — 'sudo systemctl enable docker' or a reboot won't bring the stack back"
  fi
fi

# Read one KEY=VALUE from .env without executing it (a password may contain $,
# backticks, quotes). Last assignment wins, matching docker compose.
envval() {
  [ -f .env ] || return 0
  grep -E "^[[:space:]]*$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- \
    | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//'
}

echo "== .env =="
if [ -f .env ]; then
  ok ".env present"

  web_bind="$(envval WEB_BIND)"
  if [ -z "$web_bind" ]; then
    wrn "WEB_BIND unset — defaults to 127.0.0.1 (dashboard reachable only on the VPS itself)"
  elif [ "$web_bind" = "127.0.0.1" ] || [ "$web_bind" = "localhost" ]; then
    wrn "WEB_BIND is loopback — the phone can't reach it. Set it to 'tailscale ip -4'."
  elif [ "$web_bind" = "0.0.0.0" ]; then
    err "WEB_BIND is 0.0.0.0 — that publishes the dashboard on every interface. Use the Tailscale IP."
  else
    ok "WEB_BIND=$web_bind"
    if command -v tailscale >/dev/null 2>&1; then
      ts_ip="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
      if [ -n "$ts_ip" ] && [ "$ts_ip" != "$web_bind" ]; then
        wrn "WEB_BIND ($web_bind) != current tailscale ip ($ts_ip) — stale after a node re-login?"
      fi
    fi
  fi

  api_bind="$(envval API_BIND)"
  case "${api_bind:-127.0.0.1}" in
    127.0.0.1|localhost) ok "API_BIND is loopback" ;;
    *) wrn "API_BIND=$api_bind is not loopback — nothing but 'web' needs the API" ;;
  esac

  if [ -n "$(envval DEADPARROTS_SMTP_HOST)" ] && [ -z "$(envval DEADPARROTS_SMTP_USERNAME)" ]; then
    wrn "DEADPARROTS_SMTP_HOST set but DEADPARROTS_SMTP_USERNAME empty — the nflverse failure email will likely not send"
  fi
else
  wrn ".env missing — 'cp .env.example .env' and set WEB_BIND (deploy/README.md step 3). Defaults are loopback-only."
fi

echo "== compose config =="
if docker compose config -q >/dev/null 2>&1; then
  ok "docker-compose.yml + .env parse and merge cleanly"
else
  err "'docker compose config' failed — run it without -q to see the error"
fi

echo "== data dir =="
if [ -d data ]; then
  ok "./data present (bind-mounted to /data — persists across rebuilds)"
else
  note "./data will be created on first start"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "preflight: FAILED — fix the FAIL lines above before 'docker compose up -d'."
  exit 1
elif [ "$warn" -ne 0 ]; then
  echo "preflight: passed with warnings — review the WARN lines."
  exit 0
else
  echo "preflight: all good."
  exit 0
fi
