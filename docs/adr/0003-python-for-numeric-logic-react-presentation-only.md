# Python owns all numeric logic; React/TypeScript is presentation only

The app is a React SPA, but every calculation — Yahoo/nflverse ingestion, the RIP TIDE scoring engine, projections, the Monte Carlo simulations, and the strategic-layer formulas — lives in a Python FastAPI backend. The frontend renders and handles interaction; it performs no scoring or projection math. We rejected a Next.js fullstack app because it would force either a bridge to Python for the analytics anyway or a reimplementation of the scoring engine in TypeScript.

## Consequences

- The scoring engine is validated once, in one language, against 2025 Yahoo actuals, and is the single source of truth for points. There is no second implementation to keep in sync.
- Two deployables (API + static frontend) instead of one, coordinated by Docker Compose.
- nflverse (`nflreadpy`) and the `ffanalytics` R sidecar are both in the backend's world, not the frontend's.
- Reversing this (e.g. moving scoring into the client for offline use) would mean reimplementing and re-validating the engine — treat as effectively permanent.
