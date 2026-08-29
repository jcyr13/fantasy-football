from __future__ import annotations

from collections.abc import Iterator

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from deadparrots.config import Settings
from deadparrots.news.schedule import NEWS_JOB_ID, register_news_poll
from deadparrots.news.tagging import NewsTargets


@pytest.fixture
def scheduler() -> Iterator[BackgroundScheduler]:
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        yield sched
    finally:
        sched.shutdown(wait=False)


def test_register_adds_one_interval_job(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data", news_poll_interval_minutes=30)

    job = register_news_poll(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        targets_provider=NewsTargets.empty,
    )

    assert job.id == NEWS_JOB_ID
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval.total_seconds() == 30 * 60
    assert [j.id for j in scheduler.get_jobs()] == [NEWS_JOB_ID]


def test_register_is_idempotent(scheduler, sqlite_conn, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    register_news_poll(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        targets_provider=NewsTargets.empty,
    )
    register_news_poll(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        targets_provider=NewsTargets.empty,
    )
    assert len(scheduler.get_jobs()) == 1


def test_registered_job_runs_a_throttled_poll(
    scheduler, sqlite_conn, tmp_path, make_fake_news_source
):
    settings = Settings(data_dir=tmp_path / "data")
    source = make_fake_news_source("espn_api_news")

    job = register_news_poll(
        scheduler,
        settings=settings,
        sqlite_conn=sqlite_conn,
        targets_provider=lambda: NewsTargets(my_roster=("Josh Allen",)),
        sources=[source],
    )
    job.func()

    assert source.calls == 1
