"""Catch-up scheduling on launch (issue #41).

The desktop app's crons only tick while it is open, so on startup any pull whose
window has already passed since its last successful run is fired now. These
cover the "what is overdue" decision (:func:`due_catchup_actions`) and the thin
scheduler-bump wrapper (:func:`run_catchup_on_launch`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import duckdb
import pytest

from deadparrots.api.history import SNAPSHOT_JOB_ID
from deadparrots.catchup import (
    CatchupAction,
    SnapshotCatchup,
    _week_games_final,
    due_catchup_actions,
    resolve_snapshot_catchup,
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


# --- _week_games_final / resolve_snapshot_catchup -------------------------


@dataclass
class _FakeSources:
    season: int
    week: int

    def assemble(self, *, season=None, week=None):
        return self


def _schedules_conn(rows: list[tuple[int, int, str]]) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB with an ``nflverse_schedules`` relation carrying the
    ``season`` / ``week`` / ``gameday`` columns ``_week_games_final`` reads."""
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE nflverse_schedules "
        "(season INTEGER, week INTEGER, gameday VARCHAR)"
    )
    conn.executemany(
        "INSERT INTO nflverse_schedules VALUES (?, ?, ?)", rows
    )
    return conn


def test_week_games_final_true_when_every_kickoff_is_in_the_past():
    conn = _schedules_conn(
        [(2026, 3, "2026-09-20"), (2026, 3, "2026-09-21"), (2026, 4, "2026-09-28")]
    )
    assert _week_games_final(conn, 2026, 3, date(2026, 9, 23)) is True


def test_week_games_final_false_while_a_kickoff_is_still_ahead():
    conn = _schedules_conn([(2026, 3, "2026-09-21"), (2026, 3, "2026-09-22")])
    # a Monday-night game on the 22nd, "today" is that Monday
    assert _week_games_final(conn, 2026, 3, date(2026, 9, 22)) is False


def test_week_games_final_false_when_the_schedule_is_not_cached():
    empty = duckdb.connect(":memory:")
    assert _week_games_final(empty, 2026, 3, date(2026, 9, 23)) is False
    assert _week_games_final(None, 2026, 3, date(2026, 9, 23)) is False


def test_resolve_snapshot_catchup_reports_week_snapshot_and_finality(
    sqlite_conn, settings
):
    conn = _schedules_conn([(2026, 3, "2026-09-20"), (2026, 3, "2026-09-21")])

    ctx = resolve_snapshot_catchup(
        duckdb_conn=conn,
        sqlite_conn=sqlite_conn,
        settings=settings,
        weekly_sources_provider=lambda: _FakeSources(season=2026, week=3),
        now=datetime(2026, 9, 23, 15, 0, tzinfo=UTC),
    )

    assert (ctx.season, ctx.week) == (2026, 3)
    assert ctx.has_snapshot is False
    assert ctx.games_final is True


def test_resolve_snapshot_catchup_is_none_without_a_weekly_source(
    sqlite_conn, settings
):
    ctx = resolve_snapshot_catchup(
        duckdb_conn=None,
        sqlite_conn=sqlite_conn,
        settings=settings,
        weekly_sources_provider=lambda: None,
        now=NOW,
    )
    assert ctx == SnapshotCatchup.none()
