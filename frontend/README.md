# frontend

React + Vite + TypeScript SPA for the Dead Parrots Dashboard. Presentation and
interaction only — no scoring or projection math
(see `../docs/adr/0003-python-for-numeric-logic-react-presentation-only.md`).

## Develop

```sh
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000
npm run lint
npm test         # vitest (jsdom)
npm run build
```

## Screens

### Issue #18

- **This Week** — `GET /api/weekly`. Opponent + likely lineup with the stated
  assumption, both totals (floor / projection / ceiling) with the Yahoo
  cross-check, favored/underdog + win %, gap drivers, swing players, and the
  recommended lineup with the max-P(win) / max-EV / floor / ceiling lineups
  alongside. The engine toggle re-queries with `?engine=threshold-rule`.
- **Lineup Lab** — `GET /api/weekly/lineup-lab/auto` + `POST
  /api/weekly/lineup-lab`. Drag players between Start / Bench / IR; the lineup is
  re-scored after every move (total / floor / ceiling / win probability).
  Illegal lineups are marked, not blocked. Best-floor / best-ceiling auto-fills
  render side by side on demand. `src/screens/LineupLab.test.tsx` drives the
  drag → recompute + illegal-lineup marking against a mocked API.

### Issue #19

- **Waiver / FA** — `GET /api/free-agents`. Rest-of-season (value-over-replacement)
  and this-week streamer lists, each row with bench-need fit, own-bye note, and
  the worth-the-priority verdict + reasons. Plus the waiver-priority readout
  (rank, drop-to-last cost, no FAAB) and the post-cutdown window flag.
- **Team Outlook** — `GET /api/team-outlook`. Team strength (league percentile,
  0–100), expected vs actual wins + luck, the contend/rebuild/hold signal with
  all of its inputs and rationale, and the bye-week crunch map with per-week
  grades.
- **Trade Desk** — `GET /api/trade-desk`. Buy-low / sell-high tables with market
  rank, model rank, signed trade edge and reasons; the desperate-team read; the
  November-28 trade-deadline countdown.
- **History** — `GET /api/history`. Every stored weekly snapshot, newest first,
  as "what the model said" beside "what happened" — with the per-player
  projected / actual / delta table once the week's outcome is backfilled.

Global chrome (`src/components/`): the top-pinned `NewsTicker` (`GET /api/news`,
pause on hover, sources open in a new tab, self-hides with a notice when all
sources fail) and the always-visible `FreshnessHeader` (`GET /api/freshness`).
