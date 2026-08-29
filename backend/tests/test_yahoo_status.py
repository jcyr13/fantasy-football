from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.yahoo.status import (
    YahooPullStatus,
    last_successful_pull_at,
    recent_yahoo_pull_statuses,
    record_yahoo_pull_status,
)

BASE = datetime(2026, 9, 22, 13, 0, 0, tzinfo=UTC)


def _status(page, status, *, pull_id, offset_min=0, error=None):
    started = BASE + timedelta(minutes=offset_min)
    return YahooPullStatus(
        pull_id=pull_id,
        source=f"yahoo:{page}",
        page=page,
        status=status,
        raw_path=f"/data/yahoo/{pull_id}/{page}.json" if status == "ok" else None,
        error=error,
        started_at=started,
        finished_at=started + timedelta(seconds=5),
    )


def test_record_and_read_back_round_trips(sqlite_conn):
    record_yahoo_pull_status(sqlite_conn, _status("matchup", "ok", pull_id="p1"))
    record_yahoo_pull_status(
        sqlite_conn,
        _status("injuries", "failed", pull_id="p1", offset_min=1, error="RuntimeError: boom"),
    )

    rows = recent_yahoo_pull_statuses(sqlite_conn)

    assert [r.page for r in rows] == ["injuries", "matchup"]  # newest first
    assert rows[0].ok is False
    assert rows[0].error == "RuntimeError: boom"
    assert rows[1].raw_path.endswith("matchup.json")


def test_last_successful_pull_at_per_page_and_overall(sqlite_conn):
    # a fully-successful early pull, then a later pull where injuries failed
    for page in ("matchup", "players", "injuries", "standings"):
        record_yahoo_pull_status(sqlite_conn, _status(page, "ok", pull_id="p1"))
    for page in ("matchup", "players", "standings"):
        record_yahoo_pull_status(
            sqlite_conn, _status(page, "ok", pull_id="p2", offset_min=60)
        )
    record_yahoo_pull_status(
        sqlite_conn, _status("injuries", "failed", pull_id="p2", offset_min=60, error="x")
    )

    assert last_successful_pull_at(sqlite_conn, "matchup") == BASE + timedelta(
        minutes=60, seconds=5
    )
    # injuries last succeeded in p1, so the freshest *complete* picture is p1's age
    assert last_successful_pull_at(sqlite_conn, "injuries") == BASE + timedelta(seconds=5)
    assert last_successful_pull_at(sqlite_conn) == BASE + timedelta(seconds=5)


def test_last_successful_pull_at_is_none_when_nothing_succeeded(sqlite_conn):
    record_yahoo_pull_status(
        sqlite_conn, _status("matchup", "failed", pull_id="p1", error="x")
    )
    assert last_successful_pull_at(sqlite_conn) is None
