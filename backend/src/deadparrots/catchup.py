from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .api.history import SNAPSHOT_JOB_ID
from .config import Settings
from .consensus.schedule import WEEKLY_JOB_ID as CONSENSUS_JOB_ID
from .consensus.status import last_successful_pull_at as last_consensus_pull_at
from .ingest.schedule import WEEKLY_JOB_ID as NFLVERSE_JOB_ID
from .ingest.status import recent_pull_statuses
from .news.schedule import NEWS_JOB_ID
from .news.status import last_successful_pull_at as last_news_pull_at
from .snapshot import get_snapshot

logger = logging.getLogger(__name__)

# Catch-up scheduling on launch (issue #41). The APScheduler crons only tick
# while the desktop app is open, and the owner's computer is off overnight, so
# on startup we re-run any scheduled pull whose window has already passed since
# its last successful run. The mechanism is deliberately small: decide what is
# overdue (:func:`due_catchup_actions`, a pure read of the status tables), then
# ask APScheduler to fire that job now (:func:`run_catchup_on_launch` via
# ``modify_job(next_run_time=...)``), which reuses the exact callable the cron
# registered — no second copy of the pull wiring.

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class CatchupAction:
    """One overdue scheduled job to fire now, with why."""

    job_id: str
    reason: str


def _previous_fire(
    now: datetime, *, weekday: int, hour: int, minute: int
) -> datetime:
    """The most recent ``weekday hh:mm`` at or before ``now`` (same tz as ``now``)."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        if candidate <= now and candidate.weekday() == weekday:
            return candidate
        candidate = (candidate - timedelta(days=1)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
    return candidate  # pragma: no cover - unreachable with a real weekday


def _last_nflverse_ok(conn: sqlite3.Connection) -> datetime | None:
    """When any nflverse dataset last pulled cleanly (newest ``ok`` row)."""
    for status in recent_pull_statuses(conn, limit=500):
        if status.ok:
            return status.finished_at
    return None


def _as_aware(value: datetime, tz: ZoneInfo) -> datetime:
    return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=UTC).astimezone(tz)


@dataclass(frozen=True)
class SnapshotCatchup:
    """The weekly-snapshot slice of the launch context: the week the latest
    Yahoo matchup pull points at, whether that week already has a snapshot, and
    whether its NFL games are all in the past."""

    season: int | None
    week: int | None
    has_snapshot: bool
    games_final: bool

    @classmethod
    def none(cls) -> SnapshotCatchup:
        return cls(season=None, week=None, has_snapshot=False, games_final=False)


def due_catchup_actions(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    now: datetime,
    snapshot: SnapshotCatchup,
) -> list[CatchupAction]:
    """Which scheduled jobs are overdue as of ``now`` and should be fired on launch.

    Pure apart from reading the pull-status tables on ``conn``. ``snapshot``
    carries the already-resolved weekly-snapshot context (see
    :func:`resolve_snapshot_catchup`)."""
    actions: list[CatchupAction] = []

    nfl_tz = ZoneInfo(settings.nflverse_cron_timezone)
    nfl_fire = _previous_fire(
        now.astimezone(nfl_tz),
        weekday=_WEEKDAYS[settings.nflverse_cron_day_of_week.lower()],
        hour=settings.nflverse_cron_hour,
        minute=settings.nflverse_cron_minute,
    )
    last_nfl = _last_nflverse_ok(conn)
    if last_nfl is None or _as_aware(last_nfl, nfl_tz) < nfl_fire:
        actions.append(
            CatchupAction(
                NFLVERSE_JOB_ID,
                _overdue_reason("nflverse refresh", last_nfl, nfl_fire, nfl_tz),
            )
        )

    con_tz = ZoneInfo(settings.consensus_cron_timezone)
    con_fire = _previous_fire(
        now.astimezone(con_tz),
        weekday=_WEEKDAYS[settings.consensus_cron_day_of_week.lower()],
        hour=settings.consensus_cron_hour,
        minute=settings.consensus_cron_minute,
    )
    last_con = last_consensus_pull_at(conn)
    if last_con is None or _as_aware(last_con, con_tz) < con_fire:
        actions.append(
            CatchupAction(
                CONSENSUS_JOB_ID,
                _overdue_reason("consensus re-score", last_con, con_fire, con_tz),
            )
        )

    # The news poll is an interval job (~30 min). Any cold start is past a
    # window; fire it once so fresh news is not 30 minutes stale on open. The
    # runner's own throttle makes a redundant fire a no-op.
    last_news = last_news_pull_at(conn)
    if last_news is None or (now - _as_aware(last_news, UTC)) >= timedelta(
        minutes=settings.news_poll_interval_minutes
    ):
        actions.append(CatchupAction(NEWS_JOB_ID, "news poll has not run this session"))

    # The Sunday snapshot: if the app was closed through the capture window, take
    # the week's snapshot now — but only once its games are final, so a
    # half-played week is never frozen, and only if the week still has none.
    if (
        snapshot.week is not None
        and snapshot.games_final
        and not snapshot.has_snapshot
    ):
        actions.append(
            CatchupAction(
                SNAPSHOT_JOB_ID,
                f"week {snapshot.week} games are final and no snapshot was captured",
            )
        )

    return actions


def _overdue_reason(
    label: str, last: datetime | None, fire: datetime, tz: ZoneInfo
) -> str:
    due = fire.strftime("%a %Y-%m-%d %H:%M %Z")
    if last is None:
        return f"{label}: never run; a pull was due {due}"
    when = _as_aware(last, tz).strftime("%a %Y-%m-%d %H:%M %Z")
    return f"{label}: last ok {when}; a pull was due {due}"


def resolve_snapshot_catchup(
    *,
    duckdb_conn: object | None,
    sqlite_conn: sqlite3.Connection,
    settings: Settings,
    weekly_sources_provider: Callable[[], object | None],
    now: datetime,
) -> SnapshotCatchup:
    """Work out the weekly-snapshot launch context: assemble the current week to
    learn its ``(season, week)``, check whether it has a snapshot, and read the
    nflverse schedule to see whether its games are all done."""
    sources = weekly_sources_provider() if weekly_sources_provider else None
    if sources is None:
        return SnapshotCatchup.none()
    try:
        assembled = sources.assemble()
    except Exception:
        logger.info("catch-up: current week is not assemblable yet; skipping snapshot")
        return SnapshotCatchup.none()

    season, week = int(assembled.season), int(assembled.week)
    has_snapshot = get_snapshot(sqlite_conn, season, week) is not None
    today = now.astimezone(ZoneInfo(settings.snapshot_cron_timezone)).date()
    return SnapshotCatchup(
        season=season,
        week=week,
        has_snapshot=has_snapshot,
        games_final=_week_games_final(duckdb_conn, season, week, today),
    )


def _week_games_final(
    duckdb_conn: object | None, season: int, week: int, today: date
) -> bool:
    """True when every game of ``season``/``week`` has a kickoff date before
    ``today`` — a conservative "the week is over" read from the nflverse
    schedule. Unknown (no parquet cached, no rows) counts as not final: the
    normal Sunday cron owns the live week."""
    if duckdb_conn is None:
        return False
    try:
        row = duckdb_conn.execute(
            'SELECT max(gameday) FROM "nflverse_schedules" '
            "WHERE season = ? AND week = ?",
            [season, week],
        ).fetchone()
    except Exception:
        return False
    if not row or row[0] is None:
        return False
    last_gameday = row[0]
    if isinstance(last_gameday, datetime):
        last_gameday = last_gameday.date()
    elif not isinstance(last_gameday, date):
        try:
            last_gameday = date.fromisoformat(str(last_gameday)[:10])
        except ValueError:
            return False
    return last_gameday < today


def run_catchup_on_launch(
    scheduler: object,
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    duckdb_conn: object | None,
    weekly_sources_provider: Callable[[], object | None],
    now: datetime | None = None,
) -> list[CatchupAction]:
    """Fire every overdue scheduled job now by bumping its ``next_run_time``.

    Returns the actions taken (for logging and tests). A job that is not
    registered is skipped with a warning rather than raising."""
    now = now or datetime.now(UTC)
    snapshot = resolve_snapshot_catchup(
        duckdb_conn=duckdb_conn,
        sqlite_conn=sqlite_conn,
        settings=settings,
        weekly_sources_provider=weekly_sources_provider,
        now=now,
    )
    actions = due_catchup_actions(sqlite_conn, settings, now=now, snapshot=snapshot)
    if not actions:
        logger.info("catch-up: nothing overdue on launch")
        return actions

    for action in actions:
        try:
            scheduler.modify_job(action.job_id, next_run_time=now)
            logger.info("catch-up: firing %s now — %s", action.job_id, action.reason)
        except Exception:
            logger.warning(
                "catch-up: could not fire %s (not registered?)", action.job_id
            )
    return actions


__all__ = [
    "CatchupAction",
    "SnapshotCatchup",
    "due_catchup_actions",
    "resolve_snapshot_catchup",
    "run_catchup_on_launch",
]
