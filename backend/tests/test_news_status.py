from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.news.status import (
    NewsPullStatus,
    last_successful_pull_at,
    latest_pull_all_failed,
    recent_news_pull_statuses,
    record_news_pull_status,
)

T0 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _status(pull_id: str, source: str, status: str, *, at: datetime) -> NewsPullStatus:
    return NewsPullStatus(
        pull_id=pull_id,
        source=source,
        status=status,
        item_count=3 if status == "ok" else None,
        raw_path=f"/data/news/{pull_id}/{source}.json" if status == "ok" else None,
        error=None if status == "ok" else "RuntimeError: boom",
        started_at=at,
        finished_at=at + timedelta(seconds=2),
    )


def test_recent_statuses_are_newest_first(sqlite_conn):
    record_news_pull_status(sqlite_conn, _status("p1", "espn-api", "ok", at=T0))
    record_news_pull_status(
        sqlite_conn, _status("p2", "espn-api", "ok", at=T0 + timedelta(minutes=30))
    )
    rows = recent_news_pull_statuses(sqlite_conn)
    assert [r.pull_id for r in rows] == ["p2", "p1"]


def test_last_successful_pull_at_tracks_the_latest_ok(sqlite_conn):
    assert last_successful_pull_at(sqlite_conn) is None
    record_news_pull_status(sqlite_conn, _status("p1", "espn-api", "ok", at=T0))
    record_news_pull_status(
        sqlite_conn, _status("p2", "yahoo-rss", "failed", at=T0 + timedelta(minutes=30))
    )
    assert last_successful_pull_at(sqlite_conn) == T0 + timedelta(seconds=2)


def test_latest_pull_all_failed_is_true_only_when_every_feed_failed(sqlite_conn):
    assert latest_pull_all_failed(sqlite_conn) is False  # no polls yet

    record_news_pull_status(sqlite_conn, _status("p1", "espn-api", "ok", at=T0))
    assert latest_pull_all_failed(sqlite_conn) is False

    t1 = T0 + timedelta(minutes=30)
    record_news_pull_status(sqlite_conn, _status("p2", "espn-api", "failed", at=t1))
    record_news_pull_status(sqlite_conn, _status("p2", "espn-rss", "failed", at=t1))
    record_news_pull_status(sqlite_conn, _status("p2", "yahoo-rss", "failed", at=t1))
    assert latest_pull_all_failed(sqlite_conn) is True

    t2 = T0 + timedelta(minutes=60)
    record_news_pull_status(sqlite_conn, _status("p3", "espn-api", "failed", at=t2))
    record_news_pull_status(sqlite_conn, _status("p3", "espn-rss", "ok", at=t2))
    assert latest_pull_all_failed(sqlite_conn) is False
