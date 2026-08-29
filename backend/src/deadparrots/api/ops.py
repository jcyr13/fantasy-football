from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request

from ..consensus.status import last_successful_pull_at as consensus_last_success
from ..consensus.status import recent_consensus_pull_statuses
from ..ingest.status import recent_pull_statuses
from ..news.cache import load_cached_news
from ..news.status import last_successful_pull_at as news_last_success
from ..news.status import latest_pull_all_failed
from ..yahoo.raw import YahooRawStore
from ..yahoo.reminders import due_reminder
from ..yahoo.status import last_successful_pull_at as yahoo_last_success
from ..yahoo.status import recent_yahoo_pull_statuses
from .schemas import (
    FreshnessResponse,
    NewsItemOut,
    NewsResponse,
    NewsTagOut,
    RefreshOutcomeOut,
    RefreshResponse,
    SourceFreshnessOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])

# The ticker, the data-freshness header, and the "refresh now" / per-source
# triggers (spec issue #16). The history screen has its own router
# (``api/history.py``) since issue #17.


# --- news ----------------------------------------------------------------


@router.get("/news", response_model=NewsResponse)
def news(request: Request) -> NewsResponse:
    """The retained 48-hour ticker window, newest first, each item bucketed, plus
    whether every source failed in the latest poll (the frontend hides the
    ticker on that)."""
    conn = request.app.state.sqlite
    feed = load_cached_news(conn)
    return NewsResponse(
        fetched_at=feed.fetched_at,
        window_hours=feed.window_hours,
        all_sources_failed=latest_pull_all_failed(conn),
        items=[
            NewsItemOut(
                title=i.title,
                url=i.url,
                summary=i.summary,
                source=i.source,
                published_at=i.published_at,
                buckets=[b.value for b in i.buckets],
                tags=[
                    NewsTagOut(
                        player_name=t.player_name,
                        bucket=t.bucket.value,
                        matched_text=t.matched_text,
                    )
                    for t in i.tags
                ],
            )
            for i in feed.items
        ],
    )


# --- freshness --------------------------------------------------------


def _age(last: datetime | None) -> float | None:
    if last is None:
        return None
    now = datetime.now(UTC)
    return (now - last).total_seconds()


@router.get("/freshness", response_model=FreshnessResponse)
def freshness(request: Request) -> FreshnessResponse:
    """Per-source last successful pull, its age, and current state — nflverse,
    consensus, news, and Yahoo (one row, aggregated over the four pages) — plus
    the Yahoo staleness reminder (a reminder, never a failure alert)."""
    conn = request.app.state.sqlite
    settings = request.app.state.settings
    sources: list[SourceFreshnessOut] = []

    nfl = recent_pull_statuses(conn, limit=200)
    nfl_ok = [s for s in nfl if s.ok]
    sources.append(
        _source(
            "nflverse",
            last=max((s.finished_at for s in nfl_ok), default=None),
            failed=bool(nfl) and not nfl_ok,
        )
    )

    con_last = consensus_last_success(conn)
    con_recent = recent_consensus_pull_statuses(conn, limit=5)
    sources.append(
        _source(
            "consensus",
            last=con_last,
            failed=bool(con_recent) and not con_recent[0].ok,
        )
    )

    sources.append(
        _source(
            "news",
            last=news_last_success(conn),
            failed=latest_pull_all_failed(conn),
        )
    )

    y_last = yahoo_last_success(conn)
    y_recent = recent_yahoo_pull_statuses(conn, limit=50)
    sources.append(
        _source(
            "yahoo",
            last=y_last,
            failed=bool(y_recent) and all(not s.ok for s in y_recent[:4]),
        )
    )

    reminder = due_reminder(conn, now=datetime.now().astimezone())
    manifest = YahooRawStore(settings.data_dir).latest_manifest() or {}
    return FreshnessResponse(
        sources=sources,
        yahoo_reminder=reminder.reason if reminder else None,
        yahoo_stale_pages=list(reminder.stale_pages) if reminder else [],
        waiver_priority_needs_manual_entry=manifest.get(
            "waiver_priority_needs_manual_entry"
        ),
    )


def _source(name: str, *, last: datetime | None, failed: bool) -> SourceFreshnessOut:
    if last is None and not failed:
        state = "never"
    elif failed:
        state = "failed"
    else:
        state = "ok"
    return SourceFreshnessOut(
        source=name, last_success=last, age_seconds=_age(last), state=state
    )


# --- refresh triggers ----------------------------------------------


@dataclass(frozen=True)
class RefreshOutcome:
    source: str
    ok: bool
    detail: str


class RefreshRunner(Protocol):
    def refresh(self, sources: Iterable[str]) -> list[RefreshOutcome]: ...


_ALL_SOURCES = ("nflverse", "consensus", "news")


@router.post("/refresh", response_model=RefreshResponse)
def refresh_all(request: Request) -> RefreshResponse:
    """"Refresh now" — run the nflverse, consensus, and news pulls and report
    each outcome. The Yahoo assisted pull stays its own action
    (``POST /api/yahoo/pull``) because it needs a signed-in browser."""
    return _run_refresh(request, _ALL_SOURCES)


@router.post("/refresh/{source}", response_model=RefreshResponse)
def refresh_one(request: Request, source: str) -> RefreshResponse:
    """Refresh a single source (``nflverse`` / ``consensus`` / ``news``)."""
    if source not in _ALL_SOURCES:
        raise HTTPException(404, f"unknown source {source!r}; expected one of {_ALL_SOURCES}")
    return _run_refresh(request, (source,))


def _run_refresh(request: Request, sources: Iterable[str]) -> RefreshResponse:
    runner = getattr(request.app.state, "refresh_runner", None)
    if runner is None:
        raise HTTPException(503, "No refresh runner is configured for this server.")
    outcomes = runner.refresh(sources)
    return RefreshResponse(
        outcomes=[
            RefreshOutcomeOut(source=o.source, ok=o.ok, detail=o.detail) for o in outcomes
        ]
    )
