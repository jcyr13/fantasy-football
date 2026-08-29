# Consensus feed: the sidecar emits raw stats, the engine re-scores them

The **consensus feed** (`CONTEXT.md`, `docs/methodology.md` §2) is an external
weekly projection source — `ffanalytics`, run in the `rsidecar` container — used
as a cross-check against the model's own number and as the fallback projection
for players with thin current-season history. Spec issue #8 also allows the
**Sleeper public API** as a Week-1 stopgap.

The question was *where the RIP TIDE points come from*. `ffanalytics` and Sleeper
both apply their own scoring; neither knows RIP TIDE's 25/10/10 yards, its
distance-tiered kicking, its individual-defender schedule, or its
points-allowed tiers.

## Decision

**The sidecar (and the Sleeper stopgap) emit only raw projected stat lines. The
validated Python scoring engine re-scores them with `RIP_TIDE_RULESET`.**

This is a direct consequence of ADR-0003 (Python owns all numeric logic; the
scoring engine is validated once and is the single source of truth for points).
There is no second points implementation to keep in sync — the consensus number
shown next to the model's number is produced by the *same* `score_row` the model
uses, so a ruleset fix moves both together.

Concretely:

- `deadparrots.consensus.sources.ConsensusSource` is the swappable fetch seam,
  exactly like `LiveNflverseSource` / `BrowserYahooSource`. `RSidecarConsensusSource`
  reads the newest file the R container dropped; `SleeperConsensusSource` calls
  the public API; `FallbackConsensusSource` prefers the sidecar and falls back to
  Sleeper. The fetch itself is not unit-tested.
- `deadparrots.consensus.normalize` is pure and tested recorded-payload-in →
  `ConsensusFeed`-out. It maps each source's stat keys to the engine's canonical
  vocabulary (`SOURCE_STAT_MAPS`), resolves each player's `ScoringUnit` from its
  position, and calls the engine. If any whole scoring unit yields no scorable
  stat, it fails loudly — the signal that a source renamed a block of fields and
  the stat-key map is stale (a partial rename would otherwise pass silently as
  zero-point players).
- A `ConsensusProjection` is a single scored **mean** — "the consensus number"
  shown next to the model's own number. It carries no `floor` / `ceiling`: the
  distribution *shape* is the model's job, from positional residuals
  (`methodology.md` §3.1–§3.7), and the consensus feed must not be mistaken for
  it (`CONTEXT.md` "Consensus feed" _Avoid_).

## The sidecar is a one-shot

The `rsidecar` container runs `Rscript run.R` once and exits — it is **not** a
long-running service (spec issue #8). The systemd units in
`rsidecar/deploy/consensus-feed.{service,timer}` run
`docker compose run --rm rsidecar` weekly (the service is behind a compose
`profiles: ["sidecar"]` guard so `docker compose up` does not start it).
Independently, the `api` service's APScheduler job `consensus-weekly-pull`
re-scores the newest drop on a weekly cron; if there is no fresh drop it uses
the Sleeper stopgap, so the feed is populated every week regardless of the R
container.

## Considered alternatives

- **Score to RIP TIDE inside `run.R`** with a custom `ffanalytics` scoring
  object — rejected: a second scoring implementation in R, unvalidated against
  the 2025 Yahoo oracle, drifting from the engine on every ruleset change.
- **Take `ffanalytics`'s own points and linearly rescale** — rejected: RIP
  TIDE's kicking and points-allowed tiers are not a linear function of any
  standard scoring, so a rescale would be systematically wrong for K and DEF.
- **A long-running sidecar with its own scheduler** — rejected by the spec
  ("not long-running"); it also duplicates the APScheduler the `api` already
  hosts.

## Consequences

- Two stat-key maps (`ffanalytics`, `sleeper`) are hand-maintained in
  `normalize.py` against sources that can rename fields. The per-unit "fails
  loudly" guard, the recorded-payload tests, and `test_consensus_stat_maps.py`
  (which checks the fixtures and `run.R`'s `STAT_COLS` against the maps) are the
  tripwire.
- Adding a third consensus source later is a new `ConsensusSource` + a new entry
  in `SOURCE_STAT_MAPS` + a recorded fixture; nothing downstream changes.
- The R toolchain (`ffanalytics` from GitHub) is only in the `rsidecar` image
  and never in CI; the backend's consensus tests run against JSON fixtures.
