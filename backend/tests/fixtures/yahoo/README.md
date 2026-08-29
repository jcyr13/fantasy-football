# Yahoo assisted-pull fixtures

Recorded payloads for the four Yahoo pages the assisted pull scrapes (spec issue
#7). Each file is a structured JSON payload — the shape a
`deadparrots.yahoo.source.YahooSource` hands back for one page, and the exact
input `deadparrots.yahoo.normalize` is tested on. The browser/fetch step that
produces these from Yahoo's rendered HTML is a separate seam and is **not**
unit-tested (same split as the 2025 scoring oracle — see
`docs/scoring-oracle-capture.md`).

| File | Page | Notes |
| --- | --- | --- |
| `matchup.json` | `matchup` | Week 3, Dead Parrots vs. Norwegian Blues; both full rosters (starters + BN + IR), Yahoo projections, an injury flag |
| `players.json` | `players` | Free agents and waiver-eligible players; one row with blank `%` rostered / projection |
| `injuries.json` | `injuries` | Injury report rows across statuses (Questionable / Out / IR / Probable) |
| `standings.json` | `standings` | 12 teams, 2 divisions, **with** a waiver-priority column |
| `standings_no_waiver.json` | `standings` | Same standings **without** waiver priority — exercises the "flag for manual entry" path |

These are hand-built representative captures. To refresh from a real signed-in
pull, archive a live pull and copy its `data/yahoo/<pull_id>/*.json` here.
