from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime

from .models import (
    PlayerActual,
    SnapshotOutcome,
    SnapshotRecord,
    WeeklySnapshot,
)

# SQLite persistence for the weekly snapshot (issue #17; ADR-0014 §2). Two
# append-only tables: ``weekly_snapshot`` for the immutable capture,
# ``weekly_snapshot_outcome`` for the one-shot backfill. Neither is ever
# ``UPDATE``d — a re-capture or a re-backfill for a week that already has a row
# is an ``INSERT OR IGNORE`` no-op, and the caller is told it did not take.
# Tables are ensured lazily, the same pattern as ``ingest/status.py``.

__all__ = [
    "ensure_snapshot_tables",
    "get_outcome",
    "get_record",
    "get_snapshot",
    "list_records",
    "save_outcome",
    "save_snapshot",
]

_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS weekly_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    -- stored as TEXT: ``seed_from_snapshot_id`` is a full 64-bit *unsigned*
    -- int, which overflows SQLite's signed INTEGER.
    rng_seed TEXT NOT NULL,
    captured TEXT NOT NULL,
    UNIQUE (season, week)
)
"""

_OUTCOME_DDL = """
CREATE TABLE IF NOT EXISTS weekly_snapshot_outcome (
    snapshot_id TEXT PRIMARY KEY
        REFERENCES weekly_snapshot (snapshot_id),
    backfilled_at TEXT NOT NULL,
    dead_parrots_total REAL NOT NULL,
    opponent_total REAL NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('win', 'loss', 'tie')),
    player_actuals TEXT NOT NULL
)
"""

_SNAPSHOT_INDEX = (
    "CREATE INDEX IF NOT EXISTS weekly_snapshot_season_week_idx "
    "ON weekly_snapshot (season, week)"
)


def ensure_snapshot_tables(conn: sqlite3.Connection) -> None:
    conn.execute(_SNAPSHOT_DDL)
    conn.execute(_OUTCOME_DDL)
    conn.execute(_SNAPSHOT_INDEX)
    conn.commit()


# --- capture ----------------------------------------------------------------


def save_snapshot(
    conn: sqlite3.Connection, snapshot: WeeklySnapshot
) -> tuple[WeeklySnapshot, bool]:
    """Persist ``snapshot`` if the week has none yet.

    Returns ``(stored, created)``. When a snapshot for the ``(season, week)``
    already exists this is a no-op and ``stored`` is the *original* row —
    the immutability guarantee (issue #17 acceptance criterion 5).
    """
    ensure_snapshot_tables(conn)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO weekly_snapshot
            (snapshot_id, season, week, created_at, rng_seed, captured)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.snapshot_id,
            snapshot.season,
            snapshot.week,
            snapshot.created_at.isoformat(),
            str(snapshot.rng_seed),
            json.dumps(snapshot.captured, separators=(",", ":")),
        ),
    )
    conn.commit()
    created = cur.rowcount == 1
    stored = get_snapshot(conn, snapshot.season, snapshot.week)
    if stored is None:  # pragma: no cover - just inserted or already present
        raise RuntimeError(
            f"snapshot for {snapshot.snapshot_id} vanished immediately after write"
        )
    return stored, created


def get_snapshot(
    conn: sqlite3.Connection, season: int, week: int
) -> WeeklySnapshot | None:
    ensure_snapshot_tables(conn)
    row = conn.execute(
        """
        SELECT snapshot_id, season, week, created_at, rng_seed, captured
        FROM weekly_snapshot WHERE season = ? AND week = ?
        """,
        (season, week),
    ).fetchone()
    return _row_to_snapshot(row) if row is not None else None


# --- outcome backfill -----------------------------------------------------


def save_outcome(conn: sqlite3.Connection, outcome: SnapshotOutcome) -> bool:
    """Persist ``outcome`` if the snapshot has not been backfilled yet.

    Returns ``True`` when the row was written, ``False`` when a backfill for the
    week already existed (it is left untouched — ADR-0014 §2).
    """
    ensure_snapshot_tables(conn)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO weekly_snapshot_outcome
            (snapshot_id, backfilled_at, dead_parrots_total, opponent_total,
             result, player_actuals)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            outcome.snapshot_id,
            outcome.backfilled_at.isoformat(),
            outcome.dead_parrots_total,
            outcome.opponent_total,
            outcome.result,
            json.dumps(
                [
                    {
                        "player_id": p.player_id,
                        "name": p.name,
                        "projected_points": p.projected_points,
                        "actual_points": p.actual_points,
                    }
                    for p in outcome.player_actuals
                ],
                separators=(",", ":"),
            ),
        ),
    )
    conn.commit()
    return cur.rowcount == 1


def get_outcome(
    conn: sqlite3.Connection, snapshot_id: str
) -> SnapshotOutcome | None:
    ensure_snapshot_tables(conn)
    row = conn.execute(
        """
        SELECT snapshot_id, backfilled_at, dead_parrots_total, opponent_total,
               result, player_actuals
        FROM weekly_snapshot_outcome WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    return _row_to_outcome(row) if row is not None else None


# --- records ------------------------------------------------------------


def get_record(
    conn: sqlite3.Connection, season: int, week: int
) -> SnapshotRecord | None:
    snapshot = get_snapshot(conn, season, week)
    if snapshot is None:
        return None
    return SnapshotRecord(
        snapshot=snapshot, outcome=get_outcome(conn, snapshot.snapshot_id)
    )


def list_records(
    conn: sqlite3.Connection, *, season: int | None = None
) -> list[SnapshotRecord]:
    """Every stored week, newest week first (optionally scoped to a season)."""
    ensure_snapshot_tables(conn)
    params: tuple[object, ...] = ()
    where = ""
    if season is not None:
        where = "WHERE season = ?"
        params = (season,)
    rows = conn.execute(
        f"""
        SELECT snapshot_id, season, week, created_at, rng_seed, captured
        FROM weekly_snapshot {where}
        ORDER BY season DESC, week DESC
        """,
        params,
    ).fetchall()
    snapshots = [_row_to_snapshot(r) for r in rows]
    return [
        SnapshotRecord(
            snapshot=s, outcome=get_outcome(conn, s.snapshot_id)
        )
        for s in snapshots
    ]


# --- row mapping ------------------------------------------------------


def _row_to_snapshot(row: tuple) -> WeeklySnapshot:
    return WeeklySnapshot(
        snapshot_id=row[0],
        season=int(row[1]),
        week=int(row[2]),
        created_at=_parse(row[3]),
        rng_seed=int(row[4]),
        captured=json.loads(row[5]),
    )


def _row_to_outcome(row: tuple) -> SnapshotOutcome:
    raw: Sequence[dict] = json.loads(row[5])
    return SnapshotOutcome(
        snapshot_id=row[0],
        backfilled_at=_parse(row[1]),
        dead_parrots_total=float(row[2]),
        opponent_total=float(row[3]),
        result=row[4],
        player_actuals=[
            PlayerActual(
                player_id=str(p["player_id"]),
                name=str(p.get("name", "")),
                projected_points=float(p["projected_points"]),
                actual_points=float(p["actual_points"]),
            )
            for p in raw
        ],
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
