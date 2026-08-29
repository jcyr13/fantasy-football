from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import FreeAgentListing, InjuryReport, MatchupSnapshot, StandingsSnapshot
from .normalize import normalize
from .pages import ALL_PAGES, YahooPage
from .raw import YahooRawStore
from .source import YahooSource
from .status import (
    PullOutcome,
    YahooPullStatus,
    ensure_yahoo_pull_status_table,
    record_yahoo_pull_status,
)

logger = logging.getLogger(__name__)

PULL_ID_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class YahooPagePullResult:
    page: YahooPage
    status: PullOutcome
    raw_path: Path | None
    normalized: Any | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class YahooPullRun:
    """The outcome of one assisted pull across all four Yahoo pages.

    A page failure is isolated — the other pages still land — and there is no
    email on failure: a stale or missing page shows up in the data-freshness
    header and drives a reminder, never an alert (spec issue #7; docs/adr/0001).
    """

    pull_id: str
    results: tuple[YahooPagePullResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> list[YahooPagePullResult]:
        return [r for r in self.results if not r.ok]

    def normalized(self, page: YahooPage) -> Any | None:
        for result in self.results:
            if result.page is page:
                return result.normalized
        return None

    @property
    def matchup(self) -> MatchupSnapshot | None:
        return self.normalized(YahooPage.MATCHUP)

    @property
    def free_agents(self) -> FreeAgentListing | None:
        return self.normalized(YahooPage.PLAYERS)

    @property
    def injuries(self) -> InjuryReport | None:
        return self.normalized(YahooPage.INJURIES)

    @property
    def standings(self) -> StandingsSnapshot | None:
        return self.normalized(YahooPage.STANDINGS)


def run_yahoo_pull(
    *,
    source: YahooSource,
    raw_store: YahooRawStore,
    conn: sqlite3.Connection,
    pages: Iterable[YahooPage] = ALL_PAGES,
    week: int | None = None,
    pulled_at: datetime | None = None,
) -> YahooPullRun:
    """Perform the one-click assisted pull: fetch, archive, and normalize every
    requested Yahoo page against the signed-in session behind ``source``.

    One timestamped pull set, one ``yahoo_pull_status`` row per page, raw
    payloads retained on disk, and a ``manifest.json`` for the run. Nothing
    calls out on failure.
    """
    ensure_yahoo_pull_status_table(conn)
    pulled_at = pulled_at or datetime.now(UTC)
    pull_id = pulled_at.strftime(PULL_ID_FORMAT)
    # A pull set is a directory named to the second; a benign fast re-run just
    # takes the next free second rather than colliding.
    while raw_store.pull_dir(pull_id).exists():
        pulled_at += timedelta(seconds=1)
        pull_id = pulled_at.strftime(PULL_ID_FORMAT)

    results: list[YahooPagePullResult] = []
    for page in pages:
        started_at = datetime.now(UTC)
        raw_path: Path | None = None
        try:
            payload = source.fetch(page, week=week)
            raw_path = raw_store.write(pull_id, payload)
            normalized = normalize(payload)
            result = YahooPagePullResult(page, "ok", raw_path, normalized, None)
            logger.info("yahoo pull %s: %s ok", pull_id, page.value)
        except Exception as exc:  # isolate one page's failure from the rest
            logger.exception("yahoo pull %s: %s failed", pull_id, page.value)
            result = YahooPagePullResult(
                page, "failed", raw_path, None, f"{type(exc).__name__}: {exc}"
            )
        results.append(result)
        record_yahoo_pull_status(
            conn,
            YahooPullStatus(
                pull_id=pull_id,
                source=page.source,
                page=page.value,
                status=result.status,
                raw_path=str(result.raw_path) if result.raw_path else None,
                error=result.error,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            ),
        )

    run = YahooPullRun(pull_id, tuple(results))
    raw_store.write_manifest(
        pull_id,
        {
            "pull_id": pull_id,
            "pulled_at": pulled_at.isoformat(),
            "source": getattr(source, "source_label", "yahoo"),
            "week": week,
            "pages": {
                r.page.value: {
                    "status": r.status,
                    "raw_path": str(r.raw_path) if r.raw_path else None,
                    "error": r.error,
                }
                for r in results
            },
        },
    )
    if not run.ok:
        # Deliberately not an alert. The freshness header and the reminder do the
        # nudging; a hard scrape error is only logged.
        logger.warning(
            "yahoo pull %s finished with %d failed page(s): %s",
            pull_id,
            len(run.failures),
            ", ".join(r.page.value for r in run.failures),
        )
    return run
