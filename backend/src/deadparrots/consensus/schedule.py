from __future__ import annotations

import sqlite3
from collections.abc import Callable

from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Settings
from ..scheduler import RECURRING_JOB_MISFIRE_GRACE_SECONDS
from .raw import ConsensusRawStore
from .runner import run_consensus_pull
from .sources import ConsensusSource, build_consensus_source, current_season_week

WEEKLY_JOB_ID = "consensus-weekly-pull"


def _pull_callable(
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    source: ConsensusSource | None,
) -> Callable[[], None]:
    raw_store = ConsensusRawStore(settings.data_dir)

    def _run() -> None:
        season, week = current_season_week(settings)
        run_consensus_pull(
            source=source or build_consensus_source(settings),
            raw_store=raw_store,
            conn=sqlite_conn,
            season=season,
            week=week,
        )

    return _run


def register_weekly_consensus_pull(
    scheduler: BaseScheduler,
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    source: ConsensusSource | None = None,
) -> Job:
    """Register the unattended weekly consensus-feed refresh on ``scheduler``.

    The job is not long-running (spec issue #8): it fetches one week of
    projections from the ``ffanalytics`` sidecar drop (falling back to Sleeper),
    re-scores them, records status, and returns.
    """
    trigger = CronTrigger(
        day_of_week=settings.consensus_cron_day_of_week,
        hour=settings.consensus_cron_hour,
        minute=settings.consensus_cron_minute,
        timezone=settings.consensus_cron_timezone,
    )
    return scheduler.add_job(
        _pull_callable(settings=settings, sqlite_conn=sqlite_conn, source=source),
        trigger=trigger,
        id=WEEKLY_JOB_ID,
        name="consensus feed weekly refresh",
        replace_existing=True,
        misfire_grace_time=RECURRING_JOB_MISFIRE_GRACE_SECONDS,
        coalesce=True,
        max_instances=1,
    )
