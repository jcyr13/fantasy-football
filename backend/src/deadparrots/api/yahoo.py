from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from deadparrots.yahoo.models import StandingsSnapshot
from deadparrots.yahoo.pages import ALL_PAGES
from deadparrots.yahoo.raw import YahooRawStore
from deadparrots.yahoo.reminders import due_reminder
from deadparrots.yahoo.runner import run_yahoo_pull
from deadparrots.yahoo.status import last_successful_pull_at, recent_yahoo_pull_statuses

router = APIRouter(tags=["yahoo"], prefix="/yahoo")

# The assisted pull's HTTP surface (spec issue #7). ``POST /yahoo/pull`` is the
# "one action"; ``GET /yahoo/status`` backs the data-freshness header and its
# staleness reminder — which is a reminder, never a failure alert.


class YahooPageResult(BaseModel):
    page: str
    status: str
    error: str | None = None


class YahooPullResponse(BaseModel):
    pull_id: str
    ok: bool
    pages: list[YahooPageResult]
    waiver_priority_needs_manual_entry: bool | None = None


class YahooFreshnessResponse(BaseModel):
    last_successful_pull: str | None
    reminder: str | None
    stale_pages: list[str]
    pages: list[YahooPageResult]


@router.post("/pull", response_model=YahooPullResponse)
def trigger_pull(request: Request) -> YahooPullResponse:
    """Run the assisted pull of all four Yahoo pages against the signed-in
    session behind the configured source.
    """
    source = getattr(request.app.state, "yahoo_source", None)
    if source is None:
        raise HTTPException(
            status_code=503,
            detail="No Yahoo assisted-pull source is configured for this server.",
        )
    settings = request.app.state.settings
    run = run_yahoo_pull(
        source=source,
        raw_store=YahooRawStore(settings.data_dir),
        conn=request.app.state.sqlite,
    )
    standings = run.standings
    return YahooPullResponse(
        pull_id=run.pull_id,
        ok=run.ok,
        pages=[
            YahooPageResult(page=r.page.value, status=r.status, error=r.error)
            for r in run.results
        ],
        waiver_priority_needs_manual_entry=(
            standings.waiver_priority_needs_manual_entry
            if isinstance(standings, StandingsSnapshot)
            else None
        ),
    )


@router.get("/status", response_model=YahooFreshnessResponse)
def freshness(request: Request) -> YahooFreshnessResponse:
    """Last successful pull, any due staleness reminder, and the newest per-page
    status — everything the data-freshness header needs.
    """
    conn = request.app.state.sqlite
    reminder = due_reminder(conn, now=datetime.now().astimezone())
    last = last_successful_pull_at(conn)

    latest_by_page: dict[str, YahooPageResult] = {}
    for status in recent_yahoo_pull_statuses(conn, limit=200):
        latest_by_page.setdefault(
            status.page,
            YahooPageResult(page=status.page, status=status.status, error=status.error),
        )

    return YahooFreshnessResponse(
        last_successful_pull=last.isoformat() if last else None,
        reminder=reminder.reason if reminder else None,
        stale_pages=list(reminder.stale_pages) if reminder else [],
        pages=[latest_by_page[p.value] for p in ALL_PAGES if p.value in latest_by_page],
    )
