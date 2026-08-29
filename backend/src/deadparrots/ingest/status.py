from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# One row per dataset per pull run: whether it succeeded, how many rows landed,
# and the error if it did not. Read back for the data-freshness header and the
# failure-alert history.

PullOutcome = Literal["ok", "failed"]

_TABLE = "nflverse_pull_status"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_id TEXT NOT NULL,
    source TEXT NOT NULL,
    dataset TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    row_count INTEGER,
    parquet_path TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {_TABLE}_dataset_finished_idx "
    f"ON {_TABLE} (dataset, finished_at)"
)


@dataclass(frozen=True)
class PullStatus:
    """A single dataset's outcome within one nflverse pull run."""

    pull_id: str
    source: str
    dataset: str
    status: PullOutcome
    row_count: int | None
    parquet_path: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def ensure_pull_status_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)
    conn.execute(_INDEX)
    conn.commit()


def record_pull_status(conn: sqlite3.Connection, status: PullStatus) -> None:
    ensure_pull_status_table(conn)
    conn.execute(
        f"""
        INSERT INTO {_TABLE}
            (pull_id, source, dataset, status, row_count, parquet_path, error,
             started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status.pull_id,
            status.source,
            status.dataset,
            status.status,
            status.row_count,
            status.parquet_path,
            status.error,
            status.started_at.isoformat(),
            status.finished_at.isoformat(),
        ),
    )
    conn.commit()


def _row_to_status(row: tuple) -> PullStatus:
    return PullStatus(
        pull_id=row[0],
        source=row[1],
        dataset=row[2],
        status=row[3],
        row_count=row[4],
        parquet_path=row[5],
        error=row[6],
        started_at=_parse(row[7]),
        finished_at=_parse(row[8]),
    )


_SELECT = f"""
    SELECT pull_id, source, dataset, status, row_count, parquet_path, error,
           started_at, finished_at
    FROM {_TABLE}
"""


def recent_pull_statuses(conn: sqlite3.Connection, limit: int = 50) -> list[PullStatus]:
    """Most recent status rows, newest first."""
    ensure_pull_status_table(conn)
    rows = conn.execute(
        f"{_SELECT} ORDER BY finished_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_status(r) for r in rows]


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
