from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# How long after a job's scheduled fire time APScheduler will still run a
# coalesced misfire. The desktop app (issue #41) is off whenever the owner's
# computer is, so a plain hour is not enough to cover "closed overnight, opened
# in the morning". Six hours catches a normal overnight gap; anything longer is
# the job of the launch catch-up sweep (``deadparrots.catchup``), which does not
# depend on APScheduler having kept a pending misfire at all.
LAUNCH_MISFIRE_GRACE_SECONDS = 6 * 60 * 60


def build_scheduler() -> AsyncIOScheduler:
    """The APScheduler instance for background jobs.

    Ticket #2 starts it with no jobs. Later tickets register the weekly nflverse
    refresh (#3), the weekly consensus pull (#8), the news poll (#15), and the
    Sunday snapshot capture (#17); issue #41 adds the on-launch catch-up sweep.
    """
    return AsyncIOScheduler()
