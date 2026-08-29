from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler() -> AsyncIOScheduler:
    """The APScheduler instance for background jobs.

    Ticket #2 starts it with no jobs. Later tickets register the weekly nflverse
    refresh (#3), the weekly consensus pull (#8), and the news poll (#15).
    """
    return AsyncIOScheduler()
