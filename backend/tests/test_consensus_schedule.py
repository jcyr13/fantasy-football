from __future__ import annotations

from collections.abc import Iterator

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from deadparrots.config import Settings
from deadparrots.consensus.schedule import WEEKLY_JOB_ID, register_weekly_consensus_pull
from deadparrots.consensus.status import recent_consensus_pull_statuses


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        yield sched
    finally:
        sched.shutdown(wait=False)


def test_register_adds_one_weekly_cron_job(scheduler, sqlite_conn, tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        consensus_cron_day_of_week="thu",
        consensus_cron_hour=7,
    )

    job = register_weekly_consensus_pull(
        scheduler, settings=settings, sqlite_conn=sqlite_conn
    )

    assert job.id == WEEKLY_JOB_ID
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["day_of_week"] == "thu"
    assert fields["hour"] == "7"
    assert [j.id for j in scheduler.get_jobs()] == [WEEKLY_JOB_ID]


def test_register_is_idempotent(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")

    register_weekly_consensus_pull(scheduler, settings=settings, sqlite_conn=sqlite_conn)
    register_weekly_consensus_pull(scheduler, settings=settings, sqlite_conn=sqlite_conn)

    assert len(scheduler.get_jobs()) == 1


def test_the_registered_job_runs_a_pull_when_fired(
    scheduler, sqlite_conn, tmp_path, fake_consensus_source
):
    settings = Settings(
        data_dir=tmp_path / "data", consensus_season=2026, consensus_week=1
    )

    job = register_weekly_consensus_pull(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        source=fake_consensus_source,
    )
    job.func()  # invoke the scheduled callable directly

    assert fake_consensus_source.calls == [(2026, 1)]
    statuses = recent_consensus_pull_statuses(sqlite_conn)
    assert statuses and statuses[0].ok and statuses[0].source == "ffanalytics"
