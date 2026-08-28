#!/bin/sh
# Stub sidecar. The consensus projection feed (ffanalytics scored to RIP TIDE
# rules; see ticket #8 and docs/adr/0003) is not implemented yet. Until then
# this container just idles with a heartbeat so `docker compose up` shows all
# three services running.
set -eu

echo "rsidecar stub: consensus feed lands in ticket #8"
while true; do
  echo "rsidecar heartbeat $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sleep 3600
done
