from __future__ import annotations

import sqlite3
from collections.abc import Callable

import duckdb
from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Settings
from ..scheduler import RECURRING_JOB_MISFIRE_GRACE_SECONDS
from .alerts import EmailAlerter, build_email_alerter
from .cache import NflverseParquetCache
from .runner import NflverseSource, run_nflverse_pull

WEEKLY_JOB_ID = "nflverse-weekly-pull"


def _pull_callable(
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    duckdb_conn: duckdb.DuckDBPyConnection,
    source: NflverseSource | None,
    alerter: EmailAlerter | None,
) -> Callable[[], None]:
    cache = NflverseParquetCache(settings.data_dir)
    resolved_alerter = alerter or build_email_alerter(settings)

    def _run() -> None:
        # Import here so the scheduler wiring stays importable without nflreadpy.
        from .source import LiveNflverseSource

        run_nflverse_pull(
            source=source or LiveNflverseSource(seasons=settings.nflverse_seasons),
            cache=cache,
            conn=sqlite_conn,
            alerter=resolved_alerter,
            duckdb_conn=duckdb_conn,
        )

    return _run


def register_weekly_nflverse_pull(
    scheduler: BaseScheduler,
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    duckdb_conn: duckdb.DuckDBPyConnection,
    source: NflverseSource | None = None,
    alerter: EmailAlerter | None = None,
) -> Job:
    """Register the unattended weekly nflverse refresh on ``scheduler``."""
    trigger = CronTrigger(
        day_of_week=settings.nflverse_cron_day_of_week,
        hour=settings.nflverse_cron_hour,
        minute=settings.nflverse_cron_minute,
        timezone=settings.nflverse_cron_timezone,
    )
    return scheduler.add_job(
        _pull_callable(
            settings=settings,
            sqlite_conn=sqlite_conn,
            duckdb_conn=duckdb_conn,
            source=source,
            alerter=alerter,
        ),
        trigger=trigger,
        id=WEEKLY_JOB_ID,
        name="nflverse weekly parquet refresh",
        replace_existing=True,
        misfire_grace_time=RECURRING_JOB_MISFIRE_GRACE_SECONDS,
        coalesce=True,
        max_instances=1,
    )
