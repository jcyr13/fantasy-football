"""Issue #17: the weekly snapshot capture is registered as one Sunday cron and,
when fired, freezes the current assembled week — idempotently (ADR-0014 §4)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from deadparrots.api.history import SNAPSHOT_JOB_ID, register_weekly_snapshot_capture
from deadparrots.config import Settings
from deadparrots.snapshot import list_records
from weekly_fixtures import FixtureWeeklyDataSources


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        yield sched
    finally:
        sched.shutdown(wait=False)


def _register(scheduler, sqlite_conn, settings, *, sources=FixtureWeeklyDataSources()):
    return register_weekly_snapshot_capture(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        sources_provider=lambda: sources,
    )


def test_register_adds_one_sunday_cron_job(scheduler, sqlite_conn, tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        snapshot_cron_day_of_week="sat",
        snapshot_cron_hour=9,
    )
    job = _register(scheduler, sqlite_conn, settings)

    assert job.id == SNAPSHOT_JOB_ID
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["day_of_week"] == "sat"
    assert fields["hour"] == "9"
    assert [j.id for j in scheduler.get_jobs()] == [SNAPSHOT_JOB_ID]


def test_register_is_idempotent(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    _register(scheduler, sqlite_conn, settings)
    _register(scheduler, sqlite_conn, settings)
    assert len(scheduler.get_jobs()) == 1


def test_firing_the_job_captures_the_week_once(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    job = _register(scheduler, sqlite_conn, settings)

    job.func()
    job.func()  # a second fire is a no-op

    records = list_records(sqlite_conn)
    assert [(r.snapshot.season, r.snapshot.week) for r in records] == [(2026, 3)]


def test_firing_without_a_data_source_is_a_logged_skip(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    job = register_weekly_snapshot_capture(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        sources_provider=lambda: None,
    )
    job.func()  # must not raise
    assert list_records(sqlite_conn) == []
