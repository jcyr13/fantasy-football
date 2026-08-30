from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, HTTPException, Request

from ..config import Settings
from ..scheduler import LAUNCH_MISFIRE_GRACE_SECONDS
from ..snapshot import (
    SnapshotRecord,
    WeeklySnapshot,
    build_outcome,
    get_outcome,
    get_record,
    get_snapshot,
    list_records,
    save_outcome,
    save_snapshot,
    snapshot_id_for,
)
from ..weekly import AssembledWeek, build_weekly_view
from ._deps import assembled_week
from .schemas import (
    CaptureResponse,
    HistoryRecordOut,
    HistoryResponse,
    OutcomeBackfillRequest,
)
from .serialize import (
    serialize_free_agents,
    serialize_history_record,
    serialize_team_outlook,
    serialize_trade_desk,
    serialize_weekly_view,
)
from .weekly_sources import WeeklyDataSources

logger = logging.getLogger(__name__)

router = APIRouter(tags=["history"])

# Weekly snapshot persistence + outcome backfill (issue #17; ADR-0014). The
# captured payload is the four screen contracts frozen from one
# ``build_weekly_view``; the outcome is backfilled into its own table so the
# capture is never mutated. ``GET /api/history`` is no longer "pending".

SNAPSHOT_JOB_ID = "weekly-snapshot-capture"


# --- capture orchestration ---------------------------------------------


def build_captured_payload(assembled: AssembledWeek) -> dict[str, object]:
    """The immutable payload: the JSON of ``GET /api/weekly`` +
    ``/api/team-outlook`` + ``/api/trade-desk`` + ``/api/free-agents`` for the
    week, from one assembled view so every layer shares the ``rng_seed``
    (ADR-0014 §1)."""
    view = build_weekly_view(assembled)
    caveats = view.assembled.caveats
    return {
        "weekly": serialize_weekly_view(view).model_dump(mode="json"),
        "team_outlook": serialize_team_outlook(view.outlook, caveats).model_dump(
            mode="json"
        ),
        "trade_desk": serialize_trade_desk(view.trade, caveats).model_dump(
            mode="json"
        ),
        "free_agents": serialize_free_agents(view.waiver, caveats).model_dump(
            mode="json"
        ),
    }


def capture_week(
    assembled: AssembledWeek,
    conn: sqlite3.Connection,
    *,
    created_at: datetime | None = None,
) -> tuple[SnapshotRecord, bool]:
    """Freeze ``assembled`` as this week's snapshot if it has none yet.

    Returns ``(record, created)``; ``created`` is ``False`` when a snapshot for
    the week already existed, in which case the stored one is returned
    unchanged (issue #17 acceptance criterion 5)."""
    snapshot = WeeklySnapshot(
        snapshot_id=snapshot_id_for(assembled.season, assembled.week),
        season=assembled.season,
        week=assembled.week,
        created_at=created_at or datetime.now(UTC),
        rng_seed=assembled.rng_seed,
        captured=build_captured_payload(assembled),
    )
    stored, created = save_snapshot(conn, snapshot)
    record = SnapshotRecord(
        snapshot=stored, outcome=get_outcome(conn, stored.snapshot_id)
    )
    return record, created


# --- endpoints -------------------------------------------------------


def _season(request: Request) -> int:
    return request.app.state.settings.season


@router.get("/history", response_model=HistoryResponse)
def history(request: Request) -> HistoryResponse:
    """Every stored weekly snapshot for the configured season, newest week
    first, each with its frozen ``captured`` payload and its ``outcome`` (null
    until games are backfilled)."""
    conn: sqlite3.Connection = request.app.state.sqlite
    records = list_records(conn, season=_season(request))
    return HistoryResponse(
        pending=False,
        reason="",
        snapshots=[serialize_history_record(r) for r in records],
    )


@router.get("/history/{week}", response_model=HistoryRecordOut)
def history_week(request: Request, week: int) -> HistoryRecordOut:
    """One week's snapshot for the configured season, 404 if none was captured."""
    conn: sqlite3.Connection = request.app.state.sqlite
    season = _season(request)
    record = get_record(conn, season, week)
    if record is None:
        raise HTTPException(404, f"no snapshot for season {season} week {week}")
    return serialize_history_record(record)


@router.post("/history/capture", response_model=CaptureResponse)
def history_capture(request: Request, week: int | None = None) -> CaptureResponse:
    """Capture the current assembled week (``?week=`` pins one). Idempotent:
    ``created`` is ``False`` and the original is returned when the week already
    has a snapshot."""
    conn: sqlite3.Connection = request.app.state.sqlite
    assembled = assembled_week(request, week=week)
    record, created = capture_week(assembled, conn)
    return CaptureResponse(
        created=created, record=serialize_history_record(record)
    )


@router.post("/history/{week}/outcome", response_model=HistoryRecordOut)
def history_backfill_outcome(
    request: Request, week: int, body: OutcomeBackfillRequest
) -> HistoryRecordOut:
    """Backfill the week's actual outcome onto its snapshot. ``404`` if the week
    has no snapshot, ``409`` if it was already backfilled (the first backfill is
    never overwritten — ADR-0014 §2)."""
    conn: sqlite3.Connection = request.app.state.sqlite
    season = _season(request)
    snapshot = get_snapshot(conn, season, week)
    if snapshot is None:
        raise HTTPException(404, f"no snapshot for season {season} week {week}")
    outcome = build_outcome(
        snapshot,
        dead_parrots_total=body.dead_parrots_total,
        opponent_total=body.opponent_total,
        player_actuals=body.player_actuals,
    )
    if not save_outcome(conn, outcome):
        raise HTTPException(
            409, f"season {season} week {week} already has a backfilled outcome"
        )
    record = get_record(conn, season, week)
    if record is None:  # pragma: no cover - just wrote it
        raise HTTPException(500, "outcome saved but the record could not be read back")
    return serialize_history_record(record)


# --- weekly capture cron --------------------------------------------


def _capture_callable(
    *,
    sqlite_conn: sqlite3.Connection,
    sources_provider: Callable[[], WeeklyDataSources | None],
) -> Callable[[], None]:
    def _run() -> None:
        sources = sources_provider()
        if sources is None:
            logger.info("weekly snapshot capture skipped: no weekly data source")
            return
        try:
            assembled = sources.assemble()
        except Exception:
            logger.warning("weekly snapshot capture skipped: week not assemblable")
            return
        _, created = capture_week(assembled, sqlite_conn)
        logger.info(
            "weekly snapshot capture: season %s week %s (%s)",
            assembled.season,
            assembled.week,
            "captured" if created else "already present",
        )

    return _run


def register_weekly_snapshot_capture(
    scheduler: BaseScheduler,
    *,
    settings: Settings,
    sqlite_conn: sqlite3.Connection,
    sources_provider: Callable[[], WeeklyDataSources | None],
) -> Job:
    """Register the Sunday-late-morning snapshot capture on ``scheduler``.

    The write is ``INSERT OR IGNORE`` so a missed, re-fired, or raced run is
    harmless — the first capture for a ``(season, week)`` wins (ADR-0014 §4).
    """
    trigger = CronTrigger(
        day_of_week=settings.snapshot_cron_day_of_week,
        hour=settings.snapshot_cron_hour,
        minute=settings.snapshot_cron_minute,
        timezone=settings.snapshot_cron_timezone,
    )
    return scheduler.add_job(
        _capture_callable(
            sqlite_conn=sqlite_conn, sources_provider=sources_provider
        ),
        trigger=trigger,
        id=SNAPSHOT_JOB_ID,
        name="weekly snapshot capture",
        replace_existing=True,
        misfire_grace_time=LAUNCH_MISFIRE_GRACE_SECONDS,
        coalesce=True,
        max_instances=1,
    )


__all__ = [
    "SNAPSHOT_JOB_ID",
    "build_captured_payload",
    "capture_week",
    "register_weekly_snapshot_capture",
    "router",
]
