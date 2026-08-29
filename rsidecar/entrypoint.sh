#!/bin/sh
# One-shot: run the ffanalytics consensus scrape once and exit (spec issue #8;
# docs/adr/0005). This container is NOT a long-lived service — a host timer
# invokes it weekly with `docker compose run --rm rsidecar`, and the api's
# APScheduler job consumes whatever it dropped into <data>/consensus/rsidecar/.
set -eu

exec Rscript /app/run.R
