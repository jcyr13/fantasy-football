from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# One row per page per assisted-pull run: whether the scrape + normalize
# succeeded, where the raw payload landed, and the error if it did not. Read back
# for the data-freshness header and to decide when a staleness reminder is due
# (spec issue #7). Unlike the nflverse pull, a failure here is never emailed —
# Yahoo staleness is a reminder, not an alert (docs/adr/0001).

PullOutcome = Literal["ok", "failed"]

_TABLE = "yahoo_pull_status"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_id TEXT NOT NULL,
    source TEXT NOT NULL,
    page TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    raw_path TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {_TABLE}_page_finished_idx "
    f"ON {_TABLE} (page, finished_at)"
)


@dataclass(frozen=True)
class YahooPullStatus:
    """One page's outcome within one assisted-pull run."""

    pull_id: str
    source: str
    page: str
    status: PullOutcome
    raw_path: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def ensure_yahoo_pull_status_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)
    conn.execute(_INDEX)
    conn.commit()


def record_yahoo_pull_status(conn: sqlite3.Connection, status: YahooPullStatus) -> None:
    ensure_yahoo_pull_status_table(conn)
    conn.execute(
        f"""
        INSERT INTO {_TABLE}
            (pull_id, source, page, status, raw_path, error, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status.pull_id,
            status.source,
            status.page,
            status.status,
            status.raw_path,
            status.error,
            status.started_at.isoformat(),
            status.finished_at.isoformat(),
        ),
    )
    conn.commit()


_SELECT = f"""
    SELECT pull_id, source, page, status, raw_path, error, started_at, finished_at
    FROM {_TABLE}
"""


def recent_yahoo_pull_statuses(
    conn: sqlite3.Connection, limit: int = 50
) -> list[YahooPullStatus]:
    """Most recent status rows, newest first."""
    ensure_yahoo_pull_status_table(conn)
    rows = conn.execute(
        f"{_SELECT} ORDER BY finished_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_status(r) for r in rows]


def last_successful_pull_at(
    conn: sqlite3.Connection, page: str | None = None
) -> datetime | None:
    """When Yahoo data was last refreshed.

    With ``page``, the newest successful pull of that page. Without, the *oldest*
    of the per-page newest successes — i.e. the age of the freshest complete
    picture, so a run where one page failed does not read as fully fresh.
    """
    ensure_yahoo_pull_status_table(conn)
    if page is not None:
        row = conn.execute(
            f"{_SELECT} WHERE page = ? AND status = 'ok' "
            "ORDER BY finished_at DESC, id DESC LIMIT 1",
            (page,),
        ).fetchone()
        return _parse(row[7]) if row else None  # finished_at

    per_page = conn.execute(
        f"SELECT page, MAX(finished_at) FROM {_TABLE} WHERE status = 'ok' GROUP BY page"
    ).fetchall()
    if not per_page:
        return None
    return min(_parse(finished_at) for _, finished_at in per_page)


def _row_to_status(row: tuple) -> YahooPullStatus:
    return YahooPullStatus(
        pull_id=row[0],
        source=row[1],
        page=row[2],
        status=row[3],
        raw_path=row[4],
        error=row[5],
        started_at=_parse(row[6]),
        finished_at=_parse(row[7]),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
