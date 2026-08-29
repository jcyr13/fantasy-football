# The 2025 Yahoo scoring oracle

The RIP TIDE scoring engine (`deadparrots.scoring`) is a pure function and is
**not trusted** until it reproduces real 2025 Yahoo per-player weekly fantasy
points *exactly* for every offense / kicker / team-DEF player-week (spec issue
\#1, "Validation gate (hard)"), and to within **±1.0** for every individual-
defender ("D" slot) player-week with each out-of-tolerance week catalogued and
explained (ticket \#5). Those checks are `backend/tests/test_scoring_gate.py` and
`backend/tests/test_scoring_idp_gate.py` (`pytest -m gate`), running against
these committed fixtures:

| File | What it holds |
| --- | --- |
| `tests/fixtures/scoring/yahoo_2025_box_scores.raw.json` | the raw scrape — `{"<name>\|<week>": [yahoo_total, [[stat label, count], …]]}` |
| `tests/fixtures/scoring/yahoo_2025_oracle.json` | Yahoo's own weekly total per scoring entity (derived) |
| `tests/fixtures/scoring/yahoo_2025_stat_rows.json` | the matching stat lines the engine scores (derived) |
| `tests/fixtures/scoring/yahoo_2025_idp_outliers.json` | hand-maintained catalogue of D-slot player-weeks outside ±1.0, each with a stated cause |

The two derived files are regenerated from the raw one by:

```bash
cd backend
uv run python -m deadparrots.scoring.oracle build
```

A gate test asserts the committed derived files always match a fresh `build`, so
they cannot drift.

---

## Why a scrape, not `yfpy`

Yahoo's Fantasy Sports API needs a developer app with the **Fantasy Sports**
permission. That permission is **not offered** on the league owner's Yahoo
developer account (only "OpenID Connect" and a regional auction scope appear on
the app-creation form), and an OAuth token minted without it is rejected with
`oauth_problem="additional_authorization_required"`. So the oracle is captured by
reading Yahoo's own rendered box scores instead.

## What was captured

The **archived 2025 league** — Yahoo assigns a new league id per season; 2025 is
`195010` (2026 is `735806`). Reach it from the league page's season dropdown, or
directly:

```
https://football.fantasysports.yahoo.com/2025/f1/195010/<teamId 1-12>?week=<N>
```

Each team-week page lists every rostered player (starters **and** bench) with a
stat-by-stat breakdown — stat label, count, points-per, fantasy points — plus
Yahoo's total. The scrape records `[total, [[label, count], …]]` per player-week.

**Sample scope:** weeks **1, 5, 9, 13**, all 12 teams — 597 offense / kicker /
team-DEF player-weeks spanning every position and scoring situation (all FG
bands, every points-allowed tier, 2-point conversions, sacks, INTs, return
yards, defensive TDs, safeties, blocked kicks), plus **47 individual-defender
player-weeks** (solo/assisted tackles, sacks, TFLs, passes defended, forced
fumbles, an interception, a turnover return). Enough to pin the ruleset for both
surfaces.

## Widening the sample

1. Scrape more team-week pages the same way and merge them into
   `yahoo_2025_box_scores.raw.json` (key `"<name>|<week>"`, value
   `[total, [[label, count], …]]`).
2. `uv run python -m deadparrots.scoring.oracle build`
3. `uv run pytest -m gate -v`

The transform (`records_from_box_scores`) classifies each line — team defense by
nickname, kicker by a Field-Goal/PAT line, offense by an offensive stat (or a
bare returner line), else the individual-defender ("D") slot — maps Yahoo's stat
labels to the engine's canonical keys, and raises `UnmappedStatLabelError` if the
scrape used a label the engine does not cover yet.

## What the 2025 scrape established about the ruleset

Beyond the PRD list, Yahoo's own per-stat "points per" column confirmed:

- **Return yards** (kick/punt) score **1 point per 25 yards for any player** —
  offensive players and team defense alike. The PRD omits this; the gate caught it.
- RIP TIDE scores **individual defensive plays for every player**, not just the
  D slot: **solo tackle 1.0, assisted tackle 0.5, pass defended 1.0**. An
  offensive player or kicker who makes a tackle on a return is credited. (These
  live on `IndividualDefenseRules`, shared by the offense and kicker rules.)
- The **points-allowed 21-27 band is worth 0** and Yahoo simply omits the line;
  the transform supplies a representative value (24) for a defense with no
  "Points Allowed" line so the engine buckets it correctly.
- Everything else matched the transcribed `RIP_TIDE_RULESET`: 25 / 10 / 10
  yards-per-point, 6-point TDs, −1 INT / sack taken, +2 two-point conversions;
  FG bands 3 / 3 / 3 / 4 / 5; PAT ±1; team DEF sack/INT/FR/TD/safety/block =
  2/2/1/6/2/2, TFL 1, points-allowed schedule 10/7/4/1/0/−1/−4.

## The individual-defender ("D") slot

IDP is a **separate scoring surface** from team DEF (spec issue #1, "IDP / D
slot"). It lives on `IndividualDefenseRules` — the same object whose
`solo_tackle` / `assisted_tackle` / `pass_defended` values the offense and kicker
rules already borrowed — now carrying the full D-slot schedule: **solo tackle 1,
assisted tackle 0.5, sack 2, INT 2, forced fumble 1, fumble recovery 1, TD 6,
safety 2, pass defended 1, block kick 2, TFL 1, turnover-return yards 1 per 25**.
A `ScoringUnit.INDIVIDUAL_DEFENSE` row is scored on all of it; there is no
points-allowed bonus. `forced_fumbles` is IDP-only (team DEF scores only the
recovery), and the defender's own `Turnover Return Yards` is its own canonical
key `turnover_return_yards`, kept apart from a returner's kick/punt
`return_yards` even though both score 1 per 25 today.

The engine input source in production is `nflreadpy`'s defensive player stats
(the `idp` dataset — `def_*` columns off `load_player_stats`); the gate scores
the Yahoo-scraped stat lines directly.

**Tolerance.** Yahoo's live scorer splits solo vs. assisted tackles, half-sacks,
and TFLs slightly differently from the final NFL gamebook, so IDP is checked to
**±1.0**, not the cent. Every player-week outside that band must be listed in
`yahoo_2025_idp_outliers.json` with a `cause` (a gamebook-vs-Yahoo scorer
difference — never "engine bug"); `test_scoring_idp_gate.py` fails on any
uncatalogued outlier and on any stale catalogue entry. In the current 47-week
sample every D-slot player-week matches Yahoo exactly, so the catalogue is empty.

**What the 47-week IDP sample exercises against Yahoo actuals:** solo/assisted
tackles (45 weeks), TFL (13), passes defended (7), sacks (5), forced fumbles (2),
and one each of interception, fumble recovery, and turnover-return yardage. It
does **not** yet contain a defensive TD, safety, or blocked kick recorded by a
pure individual defender — those coefficients (`touchdown` 6, `safety` 2,
`blocked_kick` 2) are pinned only by `test_scoring_ruleset.py` against the spec
numbers, not yet by a Yahoo actual. Widen the scrape (below) with weeks that
include an IDP score / safety / block to close that gap; the transform already
maps the labels.

## Interpreting a gate failure

A systematic offset across many player-weeks is a **ruleset** gap — fix it in
`deadparrots.scoring.ruleset.RIP_TIDE_RULESET` and re-run. Still-open questions:

- **Offensive fumble lost.** `OffenseRules.fumble_lost` defaults to `0.0` (the
  PRD lists no such penalty and no fumble-lost line appeared in the sample). If a
  wider scrape shows kept players reading `2 × fumbles` low, set it to `-2.0`.
- **Points-allowed tier edges.** The PRD gives only the seven bonus values; the
  bucket edges (0 / 6 / 13 / 20 / 27 / 34) are the standard Yahoo defaults and
  every band the sample exercised matched. Confirm against the league settings
  PDF if a wider scrape disagrees.

A lone player-week that does not generalise is an NFL-gamebook-vs-Yahoo scorer
difference — catalogue it in the PR that widens the fixture; don't bend the
ruleset to it.
