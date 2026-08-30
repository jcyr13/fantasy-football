"""Catch-up scheduling on launch (issue #41).

The desktop app's crons only tick while it is open, so on startup any pull whose
window has already passed since its last successful run is fired now. These
cover the "what is overdue" decision (:func:`due_catchup_actions`) and the thin
scheduler-bump wrapper (:func:`run_catchup_on_launch`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deadparrots.api.history import SNAPSHOT_JOB_ID
from deadparrots.catchup import (
    CatchupAction,
    SnapshotCatchup,
    due_catchup_actions,
    run_catchup_on_launch,
)
from deadparrots.config import Settings
from deadparrots.consensus.schedule import WEEKLY_JOB_ID as CONSENSUS_JOB_ID
from deadparrots.consensus.status import (
    ConsensusPullStatus,
    record_consensus_pull_status,
)
from deadparrots.ingest.schedule import WEEKLY_JOB_ID as NFLVERSE_JOB_ID
from deadparrots.ingest.status import PullStatus, record_pull_status
from deadparrots.news.schedule import NEWS_JOB_ID
from deadparrots.news.status import NewsPullStatus, record_news_pull_status

# A Wednesday, 15:00 UTC == 11:00 America/New_York. Past this week's Tuesday
# 08:00 nflverse fire and this week's Wednesday 06:00 consensus fire.
NOW = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)


def _record_nflverse_ok(conn, finished_at: datetime) -> None:
    record_pull_status(
        conn,
        PullStatus(
            pull_id=finished_at.strftime("%Y%m%dT%H%M%SZ"),
            source="nflverse",
            dataset="player_stats",
            status="ok",
            row_count=1,
            parquet_path="x.parquet",
            error=None,
            started_at=finished_at - timedelta(minutes=1),
            finished_at=finished_at,
        ),
    )


def _record_consensus_ok(conn, finished_at: datetime) -> None:
    record_consensus_pull_status(
        conn,
        ConsensusPullStatus(
            pull_id=finished_at.strftime("%Y%m%dT%H%M%SZ"),
            source="sleeper",
            season=2026,
            week=4,
            status="ok",
            projection_count=1,
            raw_path="x.json",
            error=None,
            started_at=finished_at - timedelta(minutes=1),
            finished_at=finished_at,
        ),
    )


def _record_news_ok(conn, finished_at: datetime) -> None:
    record_news_pull_status(
        conn,
        NewsPullStatus(
            pull_id=finished_at.strftime("%Y%m%dT%H%M%SZ"),
            source="espn-api",
            status="ok",
            item_count=1,
            raw_path="x.json",
            error=None,
            started_at=finished_at - timedelta(minutes=1),
            finished_at=finished_at,
        ),
    )


def _job_ids(actions: list[CatchupAction]) -> set[str]:
    return {a.job_id for a in actions}


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_nothing_recorded_means_all_three_recurring_pulls_are_overdue(
    sqlite_conn, settings
):
    actions = due_catchup_actions(
        sqlite_conn, settings, now=NOW, snapshot=SnapshotCatchup.none()
    )

    assert _job_ids(actions) == {NFLVERSE_JOB_ID, CONSENSUS_JOB_ID, NEWS_JOB_ID}
    assert all("never" in a.reason or "not run" in a.reason for a in actions)


def test_recent_successful_pulls_are_not_overdue(sqlite_conn, settings):
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=1))

    actions = due_catchup_actions(
        sqlite_conn, settings, now=NOW, snapshot=SnapshotCatchup.none()
    )

    assert actions == []


def test_a_pull_older_than_its_last_cron_window_is_overdue(sqlite_conn, settings):
    # nflverse ran a week ago — before this week's Tuesday 08:00 ET fire.
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(days=8))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=1))

    actions = due_catchup_actions(
        sqlite_conn, settings, now=NOW, snapshot=SnapshotCatchup.none()
    )

    assert _job_ids(actions) == {NFLVERSE_JOB_ID}
    assert "last ok" in actions[0].reason


def test_stale_news_poll_is_overdue(sqlite_conn, settings):
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=45))

    actions = due_catchup_actions(
        sqlite_conn, settings, now=NOW, snapshot=SnapshotCatchup.none()
    )

    assert _job_ids(actions) == {NEWS_JOB_ID}


def test_snapshot_is_captured_when_week_is_final_and_unsnapshotted(
    sqlite_conn, settings
):
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=1))

    actions = due_catchup_actions(
        sqlite_conn,
        settings,
        now=NOW,
        snapshot=SnapshotCatchup(
            season=2026, week=3, has_snapshot=False, games_final=True
        ),
    )

    assert _job_ids(actions) == {SNAPSHOT_JOB_ID}
    assert "week 3" in actions[0].reason


def test_snapshot_is_not_recaptured_and_not_taken_mid_week(sqlite_conn, settings):
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=1))

    already = SnapshotCatchup(
        season=2026, week=3, has_snapshot=True, games_final=True
    )
    mid_week = SnapshotCatchup(
        season=2026, week=3, has_snapshot=False, games_final=False
    )

    assert due_catchup_actions(sqlite_conn, settings, now=NOW, snapshot=already) == []
    assert due_catchup_actions(sqlite_conn, settings, now=NOW, snapshot=mid_week) == []


# --- run_catchup_on_launch --------------------------------------------------


class _FakeScheduler:
    def __init__(self, *, missing: set[str] | None = None) -> None:
        self.bumped: list[tuple[str, datetime]] = []
        self._missing = missing or set()

    def modify_job(self, job_id: str, *, next_run_time: datetime) -> None:
        if job_id in self._missing:
            raise LookupError(f"no job {job_id}")
        self.bumped.append((job_id, next_run_time))


def test_run_catchup_bumps_every_overdue_job(sqlite_conn, settings):
    scheduler = _FakeScheduler()

    actions = run_catchup_on_launch(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        duckdb_conn=None,
        weekly_sources_provider=lambda: None,
        now=NOW,
    )

    assert _job_ids(actions) == {NFLVERSE_JOB_ID, CONSENSUS_JOB_ID, NEWS_JOB_ID}
    assert {j for j, _ in scheduler.bumped} == {
        NFLVERSE_JOB_ID,
        CONSENSUS_JOB_ID,
        NEWS_JOB_ID,
    }
    assert all(ts == NOW for _, ts in scheduler.bumped)


def test_run_catchup_survives_an_unregistered_job(sqlite_conn, settings):
    scheduler = _FakeScheduler(missing={CONSENSUS_JOB_ID})

    actions = run_catchup_on_launch(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        duckdb_conn=None,
        weekly_sources_provider=lambda: None,
        now=NOW,
    )

    # the decision still lists it; only the bump was skipped
    assert CONSENSUS_JOB_ID in _job_ids(actions)
    assert {j for j, _ in scheduler.bumped} == {NFLVERSE_JOB_ID, NEWS_JOB_ID}


def test_run_catchup_is_a_noop_when_nothing_is_overdue(sqlite_conn, settings):
    _record_nflverse_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_consensus_ok(sqlite_conn, NOW - timedelta(hours=2))
    _record_news_ok(sqlite_conn, NOW - timedelta(minutes=1))
    scheduler = _FakeScheduler()

    actions = run_catchup_on_launch(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        duckdb_conn=None,
        weekly_sources_provider=lambda: None,
        now=NOW,
    )

    assert actions == []
    assert scheduler.bumped == []
