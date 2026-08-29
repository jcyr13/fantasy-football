from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .cache import replace_cached_news
from .feed import build_news_feed
from .models import NewsFeed
from .normalize import ParsedArticle, normalize_payloads
from .params import DEFAULT_NEWS_PARAMS, NewsParams
from .raw import NewsRawStore, RawNewsPayload
from .sources import NewsSource
from .status import (
    NewsPullStatus,
    PullOutcome,
    ensure_news_pull_status_table,
    last_successful_pull_at,
    record_news_pull_status,
)
from .tagging import NewsTargets

logger = logging.getLogger(__name__)

PULL_ID_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class NewsFeedPullResult:
    """One feed's outcome within one poll. ``article_count`` is what this feed
    parsed *before* the window filter, dedupe, and tagging.
    """

    source: str
    status: PullOutcome
    raw_path: Path | None
    article_count: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class NewsPullRun:
    """The outcome of one news poll across every configured feed.

    A feed failure is isolated — the other feeds still land — and nothing is
    emailed: a dead feed shows up in the freshness header and hides the ticker
    (user stories #40, #41; ADR-0012). ``skipped`` is set when the throttle
    (spec issue #15: "at most every ~30 minutes") suppressed the fetch.
    """

    pull_id: str
    skipped: bool
    feed: NewsFeed | None
    results: tuple[NewsFeedPullResult, ...]

    @property
    def ok(self) -> bool:
        return not self.skipped and bool(self.results) and all(r.ok for r in self.results)

    @property
    def any_ok(self) -> bool:
        return any(r.ok for r in self.results)

    @property
    def failures(self) -> list[NewsFeedPullResult]:
        return [r for r in self.results if not r.ok]


def run_news_pull(
    *,
    sources: Sequence[NewsSource],
    raw_store: NewsRawStore,
    conn: sqlite3.Connection,
    targets: NewsTargets,
    params: NewsParams = DEFAULT_NEWS_PARAMS,
    now: datetime | None = None,
    throttle: bool = True,
) -> NewsPullRun:
    """Poll every feed once, archive each raw payload, normalize + tag + dedupe
    into the current 48-hour window, and replace the SQLite cache.

    One timestamped pull set, one ``news_pull_status`` row per feed, raw
    payloads retained on disk, and a ``manifest.json`` for the run. Returns
    early with ``skipped=True`` when the last successful poll was under
    ``min_poll_interval_minutes`` ago.
    """
    ensure_news_pull_status_table(conn)
    now = now or datetime.now(UTC)

    if throttle and params.min_poll_interval_minutes > 0:
        last = last_successful_pull_at(conn)
        if last is not None:
            since = now - last
            if since < timedelta(minutes=params.min_poll_interval_minutes):
                logger.info(
                    "news poll skipped: last success %.0fs ago (< %dm throttle)",
                    since.total_seconds(),
                    params.min_poll_interval_minutes,
                )
                return NewsPullRun(
                    pull_id="", skipped=True, feed=None, results=()
                )

    pulled_at = now
    pull_id = pulled_at.strftime(PULL_ID_FORMAT)
    while raw_store.pull_dir(pull_id).exists():
        pulled_at += timedelta(seconds=1)
        pull_id = pulled_at.strftime(PULL_ID_FORMAT)

    payloads: list[RawNewsPayload] = []
    articles: list[ParsedArticle] = []
    results: list[NewsFeedPullResult] = []
    manifest_sources: list[dict] = []

    # Status rows are stamped from the logical ``now``, not the wall clock, so
    # the ~30-minute throttle (which compares ``now`` against the last recorded
    # success) stays consistent when a caller drives the clock.
    for source in sources:
        started_at = now
        raw_path: Path | None = None
        try:
            fetched = source.fetch()
            for payload in fetched:
                raw_path = raw_store.write(pull_id, payload)
                manifest_sources.append(
                    {
                        "source": payload.source,
                        "fmt": payload.fmt.value,
                        "url": payload.url,
                        "fetched_at": payload.fetched_at.isoformat(),
                        "raw_path": str(raw_path),
                    }
                )
            parsed = normalize_payloads(fetched)
            payloads.extend(fetched)
            articles.extend(parsed)
            result = NewsFeedPullResult(
                source=source.source_label,
                status="ok",
                raw_path=raw_path,
                article_count=len(parsed),
                error=None,
            )
            logger.info(
                "news poll %s: %s ok (%d articles)",
                pull_id,
                source.source_label,
                len(parsed),
            )
        except Exception as exc:  # isolate one feed's failure from the rest
            logger.warning(
                "news poll %s: %s failed (%s)", pull_id, source.source_label, exc
            )
            result = NewsFeedPullResult(
                source=source.source_label,
                status="failed",
                raw_path=raw_path,
                article_count=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        record_news_pull_status(
            conn,
            NewsPullStatus(
                pull_id=pull_id,
                source=result.source,
                status=result.status,
                item_count=result.article_count,
                raw_path=str(result.raw_path) if result.raw_path else None,
                error=result.error,
                started_at=started_at,
                finished_at=now,
            ),
        )

    feed = build_news_feed(
        articles, targets, now=now, fetched_at=pulled_at, params=params
    )
    replace_cached_news(conn, feed)

    run = NewsPullRun(
        pull_id=pull_id, skipped=False, feed=feed, results=tuple(results)
    )
    raw_store.write_manifest(
        pull_id,
        {
            "pull_id": pull_id,
            "pulled_at": pulled_at.isoformat(),
            "window_hours": params.window_hours,
            "retained_items": len(feed),
            "targets_empty": targets.is_empty(),
            "sources": manifest_sources,
            "feeds": {
                r.source: {
                    "status": r.status,
                    "article_count": r.article_count,
                    "raw_path": str(r.raw_path) if r.raw_path else None,
                    "error": r.error,
                }
                for r in results
            },
        },
    )
    if not run.any_ok:
        logger.warning(
            "news poll %s: every feed failed (%s) — ticker will hide",
            pull_id,
            ", ".join(r.source for r in run.failures),
        )
    return run
