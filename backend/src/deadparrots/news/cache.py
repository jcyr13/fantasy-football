from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from ._time import ensure_utc, parse_utc
from .models import NewsBucket, NewsFeed, NewsItem, PlayerTag
from .normalize import ParsedArticle
from .params import DEFAULT_NEWS_PARAMS

# The SQLite cache of retained news items (spec issue #15: "caches results to
# SQLite with ``fetched_at``" / "Results are cached to SQLite with
# ``fetched_at``"). One row per deduped item, keyed by its dedupe key, carrying
# the poll's ``fetched_at`` and the tags as JSON.
#
# Every poll fully rebuilds the window: ``replace_cached_news`` clears the table
# and writes the current feed, so an item the feeds have stopped carrying — or
# one whose player is no longer on any target list — does not linger. The
# still-fresh rows are carried back into the next poll's feed as
# ``cached_articles`` so a story that has scrolled off an upstream feed but is
# still inside 48 hours is not lost between polls.
#
# This is application state, not a weekly snapshot — CONTEXT.md "News ticker":
# "Ephemeral — not part of a weekly snapshot." Nothing here is ever frozen into
# a ``WeeklySnapshot``.

_TABLE = "news_items"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    dedupe_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    buckets TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS {_TABLE}_published_idx ON {_TABLE} (published_at)"
)


def ensure_news_items_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)
    conn.execute(_INDEX)
    conn.commit()


def replace_cached_news(conn: sqlite3.Connection, feed: NewsFeed) -> None:
    """Replace the cache with exactly the items in ``feed``.

    A full rebuild, in one transaction: readers see the old window or the new
    one, never a partial mix. ``feed`` is already the whole retained window
    (fresh fetches plus carried-forward cached items), so this both prunes what
    aged out and drops anything no longer tagged to a current target.
    """
    ensure_news_items_table(conn)
    conn.execute(f"DELETE FROM {_TABLE}")
    conn.executemany(
        f"""
        INSERT INTO {_TABLE}
            (dedupe_key, title, url, summary, source, published_at,
             fetched_at, buckets, tags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.dedupe_key,
                item.title,
                item.url,
                item.summary,
                item.source,
                item.published_at.isoformat(),
                item.fetched_at.isoformat(),
                ",".join(b.value for b in item.buckets),
                json.dumps(
                    [
                        {
                            "player_name": t.player_name,
                            "bucket": t.bucket.value,
                            "matched_text": t.matched_text,
                        }
                        for t in item.tags
                    ]
                ),
            )
            for item in feed.items
        ],
    )
    conn.commit()


def _window_rows(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    window_hours: int,
    future_skew_minutes: int,
) -> list[tuple]:
    ensure_news_items_table(conn)
    lo = (now - timedelta(hours=window_hours)).isoformat()
    hi = (now + timedelta(minutes=future_skew_minutes)).isoformat()
    return conn.execute(
        f"""
        SELECT dedupe_key, title, url, summary, source, published_at,
               fetched_at, tags_json
        FROM {_TABLE}
        WHERE published_at >= ? AND published_at <= ?
        ORDER BY published_at DESC, title COLLATE NOCASE DESC
        """,
        (lo, hi),
    ).fetchall()


def load_cached_news(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    window_hours: int = DEFAULT_NEWS_PARAMS.window_hours,
    future_skew_minutes: int = DEFAULT_NEWS_PARAMS.future_skew_minutes,
) -> NewsFeed:
    """Rebuild a :class:`NewsFeed` from the cache, newest first, keeping only
    rows inside ``[now − window_hours, now + future_skew_minutes]`` — the same
    retention bounds ``build_news_feed`` applies on ingest. The feed's
    ``fetched_at`` is the newest row's — the last time the window was refreshed.
    """
    now = ensure_utc(now) if now is not None else datetime.now(UTC)
    rows = _window_rows(
        conn,
        now=now,
        window_hours=window_hours,
        future_skew_minutes=future_skew_minutes,
    )
    items = tuple(_row_to_item(r) for r in rows)
    fetched_at = max((i.fetched_at for i in items), default=now)
    return NewsFeed(fetched_at=fetched_at, window_hours=window_hours, items=items)


def cached_articles(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    window_hours: int = DEFAULT_NEWS_PARAMS.window_hours,
    future_skew_minutes: int = DEFAULT_NEWS_PARAMS.future_skew_minutes,
) -> list[ParsedArticle]:
    """The still-fresh cached rows as untagged :class:`ParsedArticle`, for
    carrying forward into the next poll's feed. Tags are dropped on purpose —
    the next build re-tags every article against the current targets.
    """
    rows = _window_rows(
        conn,
        now=now,
        window_hours=window_hours,
        future_skew_minutes=future_skew_minutes,
    )
    return [
        ParsedArticle(
            title=r[1],
            url=r[2],
            summary=r[3],
            source=r[4],
            published_at=parse_utc(r[5]),
        )
        for r in rows
    ]


def _row_to_item(row: tuple) -> NewsItem:
    tags = tuple(
        PlayerTag(
            player_name=t["player_name"],
            bucket=NewsBucket(t["bucket"]),
            matched_text=t["matched_text"],
        )
        for t in json.loads(row[7])
    )
    return NewsItem(
        title=row[1],
        url=row[2],
        summary=row[3],
        source=row[4],
        published_at=parse_utc(row[5]),
        fetched_at=parse_utc(row[6]),
        tags=tags,
        dedupe_key=row[0],
    )
