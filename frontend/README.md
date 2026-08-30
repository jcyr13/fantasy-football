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

## Screens (issue #18)

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

Global chrome (`src/components/`): the top-pinned `NewsTicker` (`GET /api/news`,
pause on hover, sources open in a new tab, self-hides with a notice when all
sources fail) and the always-visible `FreshnessHeader` (`GET /api/freshness`).

The remaining four screens (Waiver/FA, Team Outlook, Trade Desk, History) are
issue #19.
