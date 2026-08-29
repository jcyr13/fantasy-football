from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# One row per consensus-feed pull run: whether the fetch + normalize + re-score
# succeeded, how many projections landed, where the raw payload is, and the
# error if it did not. Read back for the data-freshness header (user story #41).
#
# Like the Yahoo assisted pull and unlike the nflverse pull, a failure here is
# never emailed: the consensus feed is a cross-check and a thin-history fallback
# (docs/methodology.md §2), so a stale feed degrades the model rather than
# breaking it — it surfaces in the freshness header, not an alert
# (docs/adr/0005).

PullOutcome = Literal["ok", "failed"]

_TABLE = "consensus_pull_status"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_id TEXT NOT NULL,
    source TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    projection_count INTEGER,
    raw_path TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {_TABLE}_week_finished_idx "
    f"ON {_TABLE} (season, week, finished_at)"
)


@dataclass(frozen=True)
class ConsensusPullStatus:
    """One consensus-feed pull run's outcome."""

    pull_id: str
    source: str
    season: int
    week: int
    status: PullOutcome
    projection_count: int | None
    raw_path: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def ensure_consensus_pull_status_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)
    conn.execute(_INDEX)
    conn.commit()


def record_consensus_pull_status(
    conn: sqlite3.Connection, status: ConsensusPullStatus
) -> None:
    ensure_consensus_pull_status_table(conn)
    conn.execute(
        f"""
        INSERT INTO {_TABLE}
            (pull_id, source, season, week, status, projection_count, raw_path,
             error, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status.pull_id,
            status.source,
            status.season,
            status.week,
            status.status,
            status.projection_count,
            status.raw_path,
            status.error,
            status.started_at.isoformat(),
            status.finished_at.isoformat(),
        ),
    )
    conn.commit()


_SELECT = f"""
    SELECT pull_id, source, season, week, status, projection_count, raw_path,
           error, started_at, finished_at
    FROM {_TABLE}
"""


def recent_consensus_pull_statuses(
    conn: sqlite3.Connection, limit: int = 50
) -> list[ConsensusPullStatus]:
    """Most recent status rows, newest first."""
    ensure_consensus_pull_status_table(conn)
    rows = conn.execute(
        f"{_SELECT} ORDER BY finished_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_status(r) for r in rows]


def last_successful_pull_at(conn: sqlite3.Connection) -> datetime | None:
    """When the consensus feed was last refreshed successfully."""
    ensure_consensus_pull_status_table(conn)
    row = conn.execute(
        f"{_SELECT} WHERE status = 'ok' ORDER BY finished_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return _parse(row[9]) if row else None  # finished_at


def _row_to_status(row: tuple) -> ConsensusPullStatus:
    return ConsensusPullStatus(
        pull_id=row[0],
        source=row[1],
        season=row[2],
        week=row[3],
        status=row[4],
        projection_count=row[5],
        raw_path=row[6],
        error=row[7],
        started_at=_parse(row[8]),
        finished_at=_parse(row[9]),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
