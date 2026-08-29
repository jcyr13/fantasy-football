"""Weekly snapshot persistence + outcome backfill (issue #17; ADR-0014).

A **Weekly snapshot** is the immutable per-week record of that week's
projections, lineups, recommendations and strategic-layer outputs, frozen as
the four screen contracts at the time they were produced (CONTEXT.md; distinct
from the **Assembled weekly view**, which is rebuilt per request and never
persisted). After games the actual outcome — both totals, the result, and
per-player actuals against the frozen projections — is backfilled into a
*separate* table so the capture row is never mutated.

* :mod:`.store` — the two append-only SQLite tables; a re-capture or re-backfill
  for a week that already has a row is an ``INSERT OR IGNORE`` no-op.
* :func:`build_outcome` — the pure join of final scores + per-player actuals
  onto a snapshot's frozen lineup.

The capture orchestration (assemble → ``build_weekly_view`` → serialize → store)
and its weekly cron live in :mod:`deadparrots.api.history`.
"""

from __future__ import annotations

from .backfill import (
    build_outcome,
    current_lineup_players,
    recommended_lineup_players,
)
from .models import (
    GameResult,
    PlayerActual,
    SnapshotOutcome,
    SnapshotRecord,
    WeeklySnapshot,
    snapshot_id_for,
)
from .store import (
    ensure_snapshot_tables,
    get_outcome,
    get_record,
    get_snapshot,
    list_records,
    save_outcome,
    save_snapshot,
)

__all__ = [
    "GameResult",
    "PlayerActual",
    "SnapshotOutcome",
    "SnapshotRecord",
    "WeeklySnapshot",
    "build_outcome",
    "current_lineup_players",
    "ensure_snapshot_tables",
    "get_outcome",
    "get_record",
    "get_snapshot",
    "list_records",
    "recommended_lineup_players",
    "save_outcome",
    "save_snapshot",
    "snapshot_id_for",
]
