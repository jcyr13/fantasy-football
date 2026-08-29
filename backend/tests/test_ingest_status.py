from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.ingest.status import (
    PullStatus,
    recent_pull_statuses,
    record_pull_status,
)

BASE = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _status(dataset, status, *, pull_id, offset_min=0, rows=None, error=None):
    started = BASE + timedelta(minutes=offset_min)
    return PullStatus(
        pull_id=pull_id,
        source=f"nflverse:{dataset}",
        dataset=dataset,
        status=status,
        row_count=rows,
        parquet_path=f"/data/nflverse/{pull_id}/{dataset}.parquet" if status == "ok" else None,
        error=error,
        started_at=started,
        finished_at=started + timedelta(seconds=30),
    )


def test_record_and_read_back_round_trips_fields(sqlite_conn):
    record_pull_status(
        sqlite_conn, _status("pbp", "ok", pull_id="p1", rows=49492)
    )
    record_pull_status(
        sqlite_conn,
        _status("injuries", "failed", pull_id="p1", offset_min=1, error="RuntimeError: boom"),
    )

    rows = recent_pull_statuses(sqlite_conn)

    assert [r.dataset for r in rows] == ["injuries", "pbp"]  # newest first
    failed = rows[0]
    assert failed.status == "failed"
    assert failed.ok is False
    assert failed.error == "RuntimeError: boom"
    assert failed.row_count is None
    ok = rows[1]
    assert ok.ok is True
    assert ok.row_count == 49492
    assert ok.parquet_path.endswith("pbp.parquet")


def test_recent_pull_statuses_honours_limit(sqlite_conn):
    for i in range(5):
        record_pull_status(
            sqlite_conn, _status("pbp", "ok", pull_id=f"p{i}", offset_min=i, rows=i)
        )

    assert len(recent_pull_statuses(sqlite_conn, limit=2)) == 2
