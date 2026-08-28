from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Backend liveness, one field per subsystem the dashboard depends on."""

    status: Literal["ok", "degraded"]
    sqlite: Literal["ok", "error"]
    duckdb: Literal["ok", "error"]
    scheduler: Literal["running", "stopped"]
    time: str


@router.get("/health")
def health(request: Request) -> HealthStatus:
    """Confirm the app-state store, the analytics store, and the scheduler are
    all reachable so the dashboard can show a real backend status.
    """
    sqlite_ok = _probe(request.app.state.sqlite)
    duckdb_ok = _probe(request.app.state.duckdb)
    scheduler_running = bool(request.app.state.scheduler.running)

    ok = sqlite_ok and duckdb_ok and scheduler_running
    return HealthStatus(
        status="ok" if ok else "degraded",
        sqlite="ok" if sqlite_ok else "error",
        duckdb="ok" if duckdb_ok else "error",
        scheduler="running" if scheduler_running else "stopped",
        time=datetime.now(UTC).isoformat(),
    )


def _probe(conn) -> bool:
    """True if ``SELECT 1`` succeeds on a DB-API-ish connection (SQLite or DuckDB)."""
    try:
        conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False
