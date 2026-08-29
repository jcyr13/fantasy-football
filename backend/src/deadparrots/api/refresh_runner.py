from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable

import duckdb

from ..config import Settings
from .ops import RefreshOutcome

logger = logging.getLogger(__name__)

# The default "refresh now" runner: it drives the same pull functions the
# scheduler uses. Each source is isolated — one failure (offline, missing
# credentials) becomes an ``ok=False`` outcome, never a 500. Tests inject a fake
# ``refresh_runner`` on ``app.state`` instead.


class AppRefreshRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        sqlite_conn: sqlite3.Connection,
        duckdb_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        self._settings = settings
        self._sqlite = sqlite_conn
        self._duckdb = duckdb_conn

    def refresh(self, sources: Iterable[str]) -> list[RefreshOutcome]:
        handlers = {
            "nflverse": self._nflverse,
            "consensus": self._consensus,
            "news": self._news,
        }
        out: list[RefreshOutcome] = []
        for name in sources:
            handler = handlers.get(name)
            if handler is None:
                out.append(RefreshOutcome(name, False, f"unknown source {name!r}"))
                continue
            try:
                out.append(handler())
            except Exception as exc:  # isolate one source's failure
                logger.exception("refresh %s failed", name)
                out.append(RefreshOutcome(name, False, f"{type(exc).__name__}: {exc}"))
        return out

    def _nflverse(self) -> RefreshOutcome:
        from ..ingest.alerts import build_email_alerter
        from ..ingest.cache import NflverseParquetCache
        from ..ingest.runner import run_nflverse_pull
        from ..ingest.source import LiveNflverseSource

        run = run_nflverse_pull(
            source=LiveNflverseSource(seasons=self._settings.nflverse_seasons),
            cache=NflverseParquetCache(self._settings.data_dir),
            conn=self._sqlite,
            alerter=build_email_alerter(self._settings),
            duckdb_conn=self._duckdb,
        )
        failed = [r.dataset for r in run.failures]
        return RefreshOutcome(
            "nflverse",
            run.ok,
            "all datasets refreshed" if run.ok else f"failed: {', '.join(failed)}",
        )

    def _consensus(self) -> RefreshOutcome:
        from ..consensus.raw import ConsensusRawStore
        from ..consensus.runner import run_consensus_pull
        from ..consensus.sources import build_consensus_source, current_season_week

        season, week = current_season_week(self._settings)
        run = run_consensus_pull(
            source=build_consensus_source(self._settings),
            raw_store=ConsensusRawStore(self._settings.data_dir),
            conn=self._sqlite,
            season=season,
            week=week,
        )
        return RefreshOutcome(
            "consensus",
            run.ok,
            f"{run.result.projection_count} projections (week {week})"
            if run.ok
            else str(run.result.error),
        )

    def _news(self) -> RefreshOutcome:
        from ..news.raw import NewsRawStore
        from ..news.runner import run_news_pull
        from ..news.sources import build_news_sources
        from ..news.targets import targets_from_latest_yahoo_pull
        from ..yahoo.raw import YahooRawStore

        run = run_news_pull(
            sources=build_news_sources(self._settings),
            raw_store=NewsRawStore(self._settings.data_dir),
            conn=self._sqlite,
            targets=targets_from_latest_yahoo_pull(YahooRawStore(self._settings.data_dir)),
            throttle=False,
        )
        n = len(run.feed.items) if run.feed is not None else 0
        return RefreshOutcome("news", not run.skipped, f"{n} items in the window")
