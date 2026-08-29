from __future__ import annotations

from fastapi import HTTPException, Request

from ..weekly import AssembledWeek
from .weekly_sources import WeeklyDataSources, WeeklyDataUnavailable

# Shared request-time helper for the weekly read endpoints: pull the assembled
# week off ``app.state``, turning a missing source or a not-yet-pulled state
# into a 503 (the same contract ``POST /api/yahoo/pull`` uses, issue #7).

__all__ = ["assembled_week"]


def assembled_week(request: Request, *, week: int | None = None) -> AssembledWeek:
    sources: WeeklyDataSources | None = getattr(
        request.app.state, "weekly_sources", None
    )
    if sources is None:
        raise HTTPException(503, "No weekly data source is configured for this server.")
    try:
        return sources.assemble(week=week)
    except WeeklyDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
