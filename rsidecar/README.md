# rsidecar

The R sidecar that will run [`ffanalytics`](https://github.com/FantasyFootballAnalytics/ffanalytics)
to produce the **consensus feed** — external weekly projections re-scored to
RIP TIDE rules — used as a cross-check and as the fallback projection for
players with thin current-season history (see `CONTEXT.md`).

**Status:** stub. `entrypoint.sh` only idles with a heartbeat. The real
pipeline is ticket #8. It is invoked on a schedule by the `api` service's
APScheduler, not run as a long-lived process, once implemented.
