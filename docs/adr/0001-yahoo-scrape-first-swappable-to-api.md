# Yahoo data: browser-scrape first, swappable to the official API

The RIP TIDE League data (matchup, players, injuries, standings) comes from Yahoo. The official Yahoo Fantasy Sports API is more robust and would let pulls run unattended, but new API access requires manual approval from Yahoo that may be slow or denied, and it does not expose Yahoo's own weekly player projections. We are therefore building v1 against a **browser-scrape of the authenticated Yahoo web pages**, behind a single source interface, and will drop in the API later if/when access is approved.

## Considered Options

- **API primary from day one** — rejected for v1: blocks the build on an approval we don't control.
- **Scrape only, forever** — rejected: brittle against DOM changes and cannot run headless on the VPS.
- **Scrape first, interface designed for a clean API swap** — chosen.

## Consequences

- The Yahoo pull needs John's signed-in desktop session, so for v1 it is a manual "assisted pull" John triggers, not a VPS cron job. Only nflverse auto-refreshes on a schedule.
- Data-freshness alerting for Yahoo is a "your data is stale, run a pull" reminder rather than a failure alert.
- The Standings page is part of the scrape set (waiver priority, Trade Desk inputs) because no structured source is available without the API.
- All Yahoo access goes through one interface; nothing downstream of it knows whether the data came from a scrape or the API.
