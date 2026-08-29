from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import ConsensusFeed
from .normalize import normalize
from .raw import ConsensusRawStore
from .sources import ConsensusSource
from .status import (
    ConsensusPullStatus,
    PullOutcome,
    ensure_consensus_pull_status_table,
    record_consensus_pull_status,
)

logger = logging.getLogger(__name__)

PULL_ID_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class ConsensusPullResult:
    source: str
    season: int
    week: int
    status: PullOutcome
    raw_path: Path | None
    feed: ConsensusFeed | None
    projection_count: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class ConsensusPullRun:
    """The outcome of one consensus-feed pull.

    One payload per run: the whole week's projections from whichever source
    answered. A failed pull is logged and shows up stale in the freshness
    header; it never emails (docs/adr/0005).
    """

    pull_id: str
    result: ConsensusPullResult

    @property
    def ok(self) -> bool:
        return self.result.ok

    @property
    def feed(self) -> ConsensusFeed | None:
        return self.result.feed


def run_consensus_pull(
    *,
    source: ConsensusSource,
    raw_store: ConsensusRawStore,
    conn: sqlite3.Connection,
    season: int,
    week: int,
    pulled_at: datetime | None = None,
) -> ConsensusPullRun:
    """Fetch one week of consensus projections, archive the raw payload, and
    normalize + re-score it to RIP TIDE rules.

    One timestamped pull set, one ``consensus_pull_status`` row, the raw payload
    retained on disk, and a ``manifest.json`` for the run.
    """
    ensure_consensus_pull_status_table(conn)
    pulled_at = pulled_at or datetime.now(UTC)
    pull_id = pulled_at.strftime(PULL_ID_FORMAT)
    # A pull set is a directory named to the second; a benign fast re-run just
    # takes the next free second rather than colliding.
    while raw_store.pull_dir(pull_id).exists():
        pulled_at += timedelta(seconds=1)
        pull_id = pulled_at.strftime(PULL_ID_FORMAT)

    started_at = datetime.now(UTC)
    raw_path: Path | None = None
    resolved_source = source.source_label
    try:
        payload = source.fetch(season, week)
        resolved_source = payload.source
        raw_path = raw_store.write(pull_id, payload)
        feed = normalize(payload)
        result = ConsensusPullResult(
            source=feed.source,
            season=season,
            week=week,
            status="ok",
            raw_path=raw_path,
            feed=feed,
            projection_count=len(feed),
            error=None,
        )
        logger.info(
            "consensus pull %s: %s ok (%d projections, week %d)",
            pull_id,
            feed.source,
            len(feed),
            week,
        )
    except Exception as exc:
        logger.warning("consensus pull %s: failed (%s)", pull_id, exc)
        result = ConsensusPullResult(
            source=resolved_source,
            season=season,
            week=week,
            status="failed",
            raw_path=raw_path,
            feed=None,
            projection_count=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    finished_at = datetime.now(UTC)
    record_consensus_pull_status(
        conn,
        ConsensusPullStatus(
            pull_id=pull_id,
            source=result.source,
            season=season,
            week=week,
            status=result.status,
            projection_count=result.projection_count,
            raw_path=str(raw_path) if raw_path else None,
            error=result.error,
            started_at=started_at,
            finished_at=finished_at,
        ),
    )
    raw_store.write_manifest(
        pull_id,
        {
            "pull_id": pull_id,
            "pulled_at": pulled_at.isoformat(),
            "source": result.source,
            "season": season,
            "week": week,
            "status": result.status,
            "projection_count": result.projection_count,
            "raw_path": str(raw_path) if raw_path else None,
            "error": result.error,
        },
    )
    return ConsensusPullRun(pull_id, result)
