from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# One row per feed per news poll: whether the fetch + parse succeeded, how many
# articles it yielded, where the raw payload landed, and the error if it did
# not. Read back for the data-freshness header (user story #41) and for the
# "hide the ticker if all sources fail" rule (user story #40).
#
# Like the Yahoo assisted pull and the consensus feed, a failure here is never
# emailed — news is a convenience strip, not analysis input, so a dead feed
# surfaces in the freshness header and hides the ticker, it does not alert
# (ADR-0012).

PullOutcome = Literal["ok", "failed"]

_TABLE = "news_pull_status"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pull_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    item_count INTEGER,
    raw_path TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {_TABLE}_source_finished_idx "
    f"ON {_TABLE} (source, finished_at)"
)


@dataclass(frozen=True)
class NewsPullStatus:
    """One feed's outcome within one news poll."""

    pull_id: str
    source: str
    status: PullOutcome
    item_count: int | None
    raw_path: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def ensure_news_pull_status_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)
    conn.execute(_INDEX)
    conn.commit()


def record_news_pull_status(conn: sqlite3.Connection, status: NewsPullStatus) -> None:
    ensure_news_pull_status_table(conn)
    conn.execute(
        f"""
        INSERT INTO {_TABLE}
            (pull_id, source, status, item_count, raw_path, error,
             started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status.pull_id,
            status.source,
            status.status,
            status.item_count,
            status.raw_path,
            status.error,
            status.started_at.isoformat(),
            status.finished_at.isoformat(),
        ),
    )
    conn.commit()


_SELECT = f"""
    SELECT pull_id, source, status, item_count, raw_path, error,
           started_at, finished_at
    FROM {_TABLE}
"""


def recent_news_pull_statuses(
    conn: sqlite3.Connection, limit: int = 50
) -> list[NewsPullStatus]:
    """Most recent status rows, newest first."""
    ensure_news_pull_status_table(conn)
    rows = conn.execute(
        f"{_SELECT} ORDER BY finished_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_status(r) for r in rows]


def last_successful_pull_at(conn: sqlite3.Connection) -> datetime | None:
    """When any feed last returned successfully — the throttle reference for the
    scheduled poll (spec issue #15: "at most every ~30 minutes").
    """
    ensure_news_pull_status_table(conn)
    row = conn.execute(
        f"{_SELECT} WHERE status = 'ok' ORDER BY finished_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return _parse(row[7]) if row else None  # finished_at


def latest_pull_all_failed(conn: sqlite3.Connection) -> bool:
    """Whether every feed in the most recent poll failed — the signal the
    frontend hides the ticker on (user story #40). ``False`` when there has
    been no poll yet.
    """
    ensure_news_pull_status_table(conn)
    row = conn.execute(
        f"SELECT pull_id FROM {_TABLE} ORDER BY finished_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return False
    statuses = conn.execute(
        f"SELECT status FROM {_TABLE} WHERE pull_id = ?", (row[0],)
    ).fetchall()
    return bool(statuses) and all(s[0] == "failed" for s in statuses)


def _row_to_status(row: tuple) -> NewsPullStatus:
    return NewsPullStatus(
        pull_id=row[0],
        source=row[1],
        status=row[2],
        item_count=row[3],
        raw_path=row[4],
        error=row[5],
        started_at=_parse(row[6]),
        finished_at=_parse(row[7]),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
