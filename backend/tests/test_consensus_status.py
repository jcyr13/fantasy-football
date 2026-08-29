from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.consensus.status import (
    ConsensusPullStatus,
    last_successful_pull_at,
    recent_consensus_pull_statuses,
    record_consensus_pull_status,
)

BASE = datetime(2026, 9, 9, 11, 0, 0, tzinfo=UTC)


def _status(pull_id, status, *, offset_min=0, count=None, error=None):
    started = BASE + timedelta(minutes=offset_min)
    return ConsensusPullStatus(
        pull_id=pull_id,
        source="ffanalytics" if status == "ok" else "consensus-fallback",
        season=2026,
        week=1,
        status=status,
        projection_count=count,
        raw_path=f"/data/consensus/{pull_id}/consensus.json" if status == "ok" else None,
        error=error,
        started_at=started,
        finished_at=started + timedelta(seconds=20),
    )


def test_record_and_read_back_round_trips_fields(sqlite_conn):
    record_consensus_pull_status(sqlite_conn, _status("p1", "ok", count=214))
    record_consensus_pull_status(
        sqlite_conn, _status("p2", "failed", offset_min=1, error="ConsensusSourceError: down")
    )

    rows = recent_consensus_pull_statuses(sqlite_conn)

    assert [r.pull_id for r in rows] == ["p2", "p1"]  # newest first
    assert rows[0].ok is False
    assert rows[0].error == "ConsensusSourceError: down"
    assert rows[1].ok is True
    assert rows[1].projection_count == 214
    assert rows[1].raw_path.endswith("consensus.json")


def test_last_successful_pull_at_ignores_failures(sqlite_conn):
    assert last_successful_pull_at(sqlite_conn) is None

    record_consensus_pull_status(sqlite_conn, _status("p1", "ok", count=10))
    record_consensus_pull_status(sqlite_conn, _status("p2", "failed", offset_min=5))

    last = last_successful_pull_at(sqlite_conn)
    assert last == BASE + timedelta(seconds=20)
