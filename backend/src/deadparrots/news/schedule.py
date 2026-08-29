from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence

from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import Settings
from .params import NewsParams
from .raw import NewsRawStore
from .runner import run_news_pull
from .sources import NewsSource, build_news_sources
from .tagging import NewsTargets

NEWS_JOB_ID = "news-poll"

# The provider that hands the poll its target lists. The assembled weekly view
# (issue #16) supplies one backed by the latest Yahoo pull's rosters and the
# free-agent shortlist; until then ``app.py`` passes one returning
# ``NewsTargets.empty()`` (the poll still archives payloads and records feed
# status, it just tags — and so retains — nothing).
TargetsProvider = Callable[[], NewsTargets]


def _poll_callable(
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    targets_provider: TargetsProvider,
    sources: Sequence[NewsSource] | None,
) -> Callable[[], None]:
    raw_store = NewsRawStore(settings.data_dir)
    params = NewsParams(
        window_hours=settings.news_window_hours,
        min_poll_interval_minutes=settings.news_poll_interval_minutes,
    )

    def _run() -> None:
        run_news_pull(
            sources=sources or build_news_sources(settings),
            raw_store=raw_store,
            conn=sqlite_conn,
            targets=targets_provider(),
            params=params,
            throttle=True,
        )

    return _run


def register_news_poll(
    scheduler: BaseScheduler,
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    targets_provider: TargetsProvider,
    sources: Sequence[NewsSource] | None = None,
) -> Job:
    """Register the recurring news poll on ``scheduler`` (spec issue #15).

    Fires on a fixed interval; the runner's own throttle enforces the "at most
    every ~30 minutes" rule even if the interval is shortened or a misfire is
    coalesced. Not long-running: each fire fetches the feeds, rebuilds the
    48-hour window, replaces the SQLite cache, and returns.
    """
    trigger = IntervalTrigger(minutes=settings.news_poll_interval_minutes)
    return scheduler.add_job(
        _poll_callable(
            settings=settings,
            sqlite_conn=sqlite_conn,
            targets_provider=targets_provider,
            sources=sources,
        ),
        trigger=trigger,
        id=NEWS_JOB_ID,
        name="news poll",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )
