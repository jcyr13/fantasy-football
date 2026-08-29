from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .pages import ALL_PAGES
from .status import last_successful_pull_at

# Yahoo data goes stale between assisted pulls, and — per docs/adr/0001 and spec
# issue #7 — that surfaces as a "your data is stale, run a pull" *reminder*, not
# a failure alert. The reminder becomes due at fixed morning checkpoints
# (CONTEXT.md: "Wed/Sat/Sun mornings"): after Tuesday's waiver run, the day
# before games, and game-day morning. If the freshest complete pull predates the
# most recent checkpoint, a pull is overdue.

# Mon=0 .. Sun=6. Wednesday, Saturday, Sunday.
REMINDER_WEEKDAYS: tuple[int, ...] = (2, 5, 6)
REMINDER_HOUR = 8


@dataclass(frozen=True)
class YahooStalenessReminder:
    """A due reminder for the data-freshness header. Not an error."""

    reason: str
    checkpoint: datetime
    last_successful_pull: datetime | None
    stale_pages: tuple[str, ...]


def most_recent_checkpoint(
    now: datetime,
    *,
    weekdays: tuple[int, ...] = REMINDER_WEEKDAYS,
    hour: int = REMINDER_HOUR,
) -> datetime:
    """The latest reminder checkpoint at or before ``now`` (same tz as ``now``)."""
    candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    for _ in range(8):
        if candidate <= now and candidate.weekday() in weekdays:
            return candidate
        candidate -= timedelta(days=1)
        candidate = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
    # Unreachable with three checkpoints a week, but keep a total function.
    return candidate  # pragma: no cover


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def due_reminder(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    weekdays: tuple[int, ...] = REMINDER_WEEKDAYS,
    hour: int = REMINDER_HOUR,
) -> YahooStalenessReminder | None:
    """The staleness reminder to show right now, or ``None`` if Yahoo data is
    current as of the most recent checkpoint.
    """
    checkpoint = most_recent_checkpoint(now, weekdays=weekdays, hour=hour)
    checkpoint_utc = _as_utc(checkpoint)

    stale_pages = tuple(
        page.value
        for page in ALL_PAGES
        if _page_is_stale(conn, page.value, checkpoint_utc)
    )
    overall = last_successful_pull_at(conn)

    if overall is None:
        return YahooStalenessReminder(
            reason="No Yahoo assisted pull on record - run one to populate the dashboard.",
            checkpoint=checkpoint,
            last_successful_pull=None,
            stale_pages=stale_pages,
        )

    if not stale_pages and _as_utc(overall) >= checkpoint_utc:
        return None

    when = _as_utc(overall).strftime("%a %Y-%m-%d %H:%M UTC")
    due = checkpoint.strftime("%a %Y-%m-%d %H:%M")
    if stale_pages:
        detail = f" Stale page(s): {', '.join(stale_pages)}."
    else:
        detail = ""
    return YahooStalenessReminder(
        reason=(
            f"Yahoo data last fully pulled {when}; a refresh was due {due}. "
            f"Run an assisted pull.{detail}"
        ),
        checkpoint=checkpoint,
        last_successful_pull=overall,
        stale_pages=stale_pages,
    )


def _page_is_stale(conn: sqlite3.Connection, page: str, checkpoint_utc: datetime) -> bool:
    last = last_successful_pull_at(conn, page)
    return last is None or _as_utc(last) < checkpoint_utc
