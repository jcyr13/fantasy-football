from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from deadparrots.config import Settings
from deadparrots.ingest.schedule import WEEKLY_JOB_ID, register_weekly_nflverse_pull


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    # Paused so registration has a real jobstore (``replace_existing`` needs one)
    # while no job actually fires during the test.
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        yield sched
    finally:
        sched.shutdown(wait=False)


def test_register_weekly_nflverse_pull_adds_one_cron_job(scheduler, sqlite_conn, tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        nflverse_cron_day_of_week="wed",
        nflverse_cron_hour=6,
    )

    job = register_weekly_nflverse_pull(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        duckdb_conn=duckdb.connect(),
    )

    assert job.id == WEEKLY_JOB_ID
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["day_of_week"] == "wed"
    assert fields["hour"] == "6"
    assert [j.id for j in scheduler.get_jobs()] == [WEEKLY_JOB_ID]


def test_register_is_idempotent(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    duck = duckdb.connect()

    register_weekly_nflverse_pull(
        scheduler, settings=settings, sqlite_conn=sqlite_conn, duckdb_conn=duck
    )
    register_weekly_nflverse_pull(
        scheduler, settings=settings, sqlite_conn=sqlite_conn, duckdb_conn=duck
    )

    assert len(scheduler.get_jobs()) == 1
