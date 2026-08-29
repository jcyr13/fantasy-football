from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from deadparrots.api.health import router as health_router
from deadparrots.config import Settings, get_settings
from deadparrots.db import connect_duckdb, init_sqlite
from deadparrots.ingest.cache import NflverseParquetCache, register_nflverse_views
from deadparrots.ingest.schedule import register_weekly_nflverse_pull
from deadparrots.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    app.state.sqlite = init_sqlite(settings.sqlite_path)
    app.state.duckdb = connect_duckdb(settings.duckdb_path)
    register_nflverse_views(app.state.duckdb, NflverseParquetCache(settings.data_dir))

    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    register_weekly_nflverse_pull(
        scheduler,
        settings=settings,
        sqlite_conn=app.state.sqlite,
        duckdb_conn=app.state.duckdb,
    )

    try:
        yield
    finally:
        app.state.scheduler.shutdown(wait=False)
        app.state.duckdb.close()
        app.state.sqlite.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Dead Parrots Dashboard API", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
