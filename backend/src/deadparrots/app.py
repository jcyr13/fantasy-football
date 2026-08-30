from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from deadparrots.api.health import router as health_router
from deadparrots.api.history import register_weekly_snapshot_capture
from deadparrots.api.history import router as history_router
from deadparrots.api.layers import router as layers_router
from deadparrots.api.ops import RefreshRunner
from deadparrots.api.ops import router as ops_router
from deadparrots.api.refresh_runner import AppRefreshRunner
from deadparrots.api.weekly import router as weekly_router
from deadparrots.api.weekly_sources import DefaultWeeklyDataSources, WeeklyDataSources
from deadparrots.api.yahoo import router as yahoo_router
from deadparrots.config import Settings, get_settings
from deadparrots.consensus.schedule import register_weekly_consensus_pull
from deadparrots.db import connect_duckdb, init_sqlite
from deadparrots.ingest.cache import NflverseParquetCache, register_nflverse_views
from deadparrots.ingest.schedule import register_weekly_nflverse_pull
from deadparrots.news.schedule import register_news_poll
from deadparrots.news.targets import build_yahoo_targets_provider
from deadparrots.scheduler import build_scheduler
from deadparrots.yahoo.scrape import build_yahoo_source
from deadparrots.yahoo.source import YahooSource

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    app.state.sqlite = init_sqlite(settings.sqlite_path)
    app.state.duckdb = connect_duckdb(settings.duckdb_path)
    register_nflverse_views(app.state.duckdb, NflverseParquetCache(settings.data_dir))

    # The assisted-pull source. A test may have injected one via create_app;
    # otherwise, if the desktop app pointed us at its Yahoo extractor endpoint
    # (issue #41), wire a browser-backed source so POST /api/yahoo/pull works.
    # With no extractor configured this stays None and the endpoint is 503.
    if getattr(app.state, "yahoo_source", None) is None:
        app.state.yahoo_source = build_yahoo_source(settings)

    # The assembled weekly view (issue #16). Unless a test injected its own,
    # read the latest Yahoo pull + nflverse parquet on demand; "refresh now"
    # drives the same pulls the scheduler runs.
    if getattr(app.state, "weekly_sources", None) is None:
        app.state.weekly_sources = DefaultWeeklyDataSources(
            settings, duckdb_conn=app.state.duckdb
        )
    if getattr(app.state, "refresh_runner", None) is None:
        app.state.refresh_runner = AppRefreshRunner(
            settings, sqlite_conn=app.state.sqlite, duckdb_conn=app.state.duckdb
        )

    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    register_weekly_nflverse_pull(
        scheduler,
        settings=settings,
        sqlite_conn=app.state.sqlite,
        duckdb_conn=app.state.duckdb,
    )
    register_weekly_consensus_pull(
        scheduler,
        settings=settings,
        sqlite_conn=app.state.sqlite,
    )
    # The news poll (spec issue #15). Targets are the Dead Parrots and
    # current-opponent rosters from the latest Yahoo assisted pull; the
    # free-agent shortlist is added by the assembled weekly view (issue #16),
    # which owns free-agent ranking. Before the first Yahoo pull the provider
    # returns empty targets and the poll retains nothing.
    register_news_poll(
        scheduler,
        settings=settings,
        sqlite_conn=app.state.sqlite,
        targets_provider=build_yahoo_targets_provider(settings),
    )
    # The weekly snapshot capture (issue #17). Reads whatever weekly data source
    # is on ``app.state`` at fire time; before the first assisted pull the
    # assembly raises and the job logs a skip.
    register_weekly_snapshot_capture(
        scheduler,
        settings=settings,
        sqlite_conn=app.state.sqlite,
        sources_provider=lambda: getattr(app.state, "weekly_sources", None),
    )

    # Catch-up on launch (issue #41): the crons above only tick while the app is
    # open, so fire any pull whose window has already passed since it last ran.
    if settings.catchup_on_launch:
        from deadparrots import catchup

        try:
            catchup.run_catchup_on_launch(
                scheduler,
                settings=settings,
                sqlite_conn=app.state.sqlite,
                duckdb_conn=app.state.duckdb,
                weekly_sources_provider=lambda: getattr(
                    app.state, "weekly_sources", None
                ),
            )
        except Exception:  # a broken sweep must never block startup
            logger.exception("launch catch-up sweep failed")

    try:
        yield
    finally:
        app.state.scheduler.shutdown(wait=False)
        app.state.duckdb.close()
        app.state.sqlite.close()


def create_app(
    settings: Settings | None = None,
    *,
    yahoo_source: YahooSource | None = None,
    weekly_sources: WeeklyDataSources | None = None,
    refresh_runner: RefreshRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="Dead Parrots Dashboard API", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    # The assisted-pull source (spec issue #7). v1 has no headless browser, so a
    # server started without one answers POST /api/yahoo/pull with 503; the
    # desktop app injects a browser-backed source here.
    app.state.yahoo_source = yahoo_source
    # Issue #16 seams: a test can inject an assembled-week provider and a
    # refresh runner; otherwise the lifespan wires the on-disk defaults.
    app.state.weekly_sources = weekly_sources
    app.state.refresh_runner = refresh_runner
    app.include_router(health_router, prefix="/api")
    app.include_router(yahoo_router, prefix="/api")
    app.include_router(weekly_router, prefix="/api")
    app.include_router(layers_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(ops_router, prefix="/api")
    return app


app = create_app()
