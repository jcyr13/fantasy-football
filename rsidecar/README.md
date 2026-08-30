# rsidecar

The R sidecar that runs [`ffanalytics`](https://github.com/FantasyFootballAnalytics/ffanalytics)
to produce the **consensus feed** — external weekly projections used as a
cross-check against the model's number and as the fallback projection for
players with thin current-season history (see `CONTEXT.md`, `docs/methodology.md`
§2, and `docs/adr/0005`).

## What it does

`run.R` scrapes ffanalytics for the current NFL week, aggregates the sources
with `projections_table()`, and writes **one** JSON file of *raw stat
projections* to `${DEADPARROTS_DATA_DIR}/consensus/rsidecar/<UTC-timestamp>.json`,
then exits. It does **not** score to RIP TIDE rules — per `docs/adr/0003` the
validated Python scoring engine is the only thing that turns stats into points,
so the backend re-scores this payload with `RIP_TIDE_RULESET`
(`deadparrots.consensus.normalize`).

## Not long-running

This container is a one-shot (spec issue #8). Nothing keeps it alive — you run
it when you want a fresh drop:

```sh
docker build -t deadparrots-rsidecar ./rsidecar
docker run --rm \
  -e DEADPARROTS_DATA_DIR=/data -e DEADPARROTS_CONSENSUS_WEEK=<week> \
  -v "$(pwd)/data:/data" \
  deadparrots-rsidecar
```

It writes one `<UTC-timestamp>.json` into `data/consensus/rsidecar/` and exits.

The dashboard's `consensus-weekly-pull` APScheduler job (Wednesday morning, plus
the catch-up on launch — `docs/adr/0016`) reads the newest drop, re-scores it,
archives the raw payload, and records a `consensus_pull_status` row. If there is
no fresh drop — Week 1, or you have not run the sidecar — that job falls back to
the **Sleeper public API** stopgap (`DEADPARROTS_CONSENSUS_SOURCE=auto`, the
default), so running the sidecar is optional.

The `deploy/consensus-feed.{service,timer}` systemd units were for the retired
VPS deployment (`docs/adr/0015`); they are dead weight now — the desktop app has
no always-on host to schedule them from.

## Payload contract (`payload_version: 1`)

Kept in lockstep with `deadparrots/consensus/normalize.py::_FFANALYTICS_STAT_MAP`
and `deadparrots/consensus/sources.py::RSIDECAR_PAYLOAD_VERSION`:

```json
{
  "source": "ffanalytics",
  "payload_version": 1,
  "season": 2026,
  "week": 1,
  "generated_at": "2026-09-09T11:00:00Z",
  "players": [
    {
      "name": "Josh Allen", "team": "BUF", "position": "QB",
      "gsis_id": "00-0034857", "source_points": 22.4,
      "stats": { "pass_yds": 265, "pass_tds": 1.8, "pass_int": 0.6, "rush_yds": 34 }
    }
  ]
}
```

`stats` keys are the canonical vocabulary the backend's `_FFANALYTICS_STAT_MAP`
translates to engine stat keys; unknown keys are ignored. Positions map to
scoring units: `QB/RB/WR/TE → offense`, `K → kicker`, `DST → team defense`,
`DL/LB/DB → individual defender (D slot)`.

## Develop

CI does not build or run this image. To iterate locally:

```sh
docker build -t deadparrots-rsidecar .
docker run --rm -e DEADPARROTS_DATA_DIR=/data -e DEADPARROTS_CONSENSUS_WEEK=1 \
  -v "$(pwd)/../data:/data" deadparrots-rsidecar
uv --project ../backend run python -m deadparrots.consensus --source rsidecar --week 1
```
