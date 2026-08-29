from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from .models import NewsBucket, NewsFeed, NewsItem, PlayerTag

# The SQLite cache of retained news items (spec issue #15: "caches results to
# SQLite with ``fetched_at``" / "Results are cached to SQLite with
# ``fetched_at``"). One row per deduped item, keyed by its dedupe key, carrying
# the poll's ``fetched_at`` and the tags as JSON. Every poll replaces the
# window: it upserts the current items and prunes anything older than
# ``window_hours`` (spec: "keeps only the last 48 hours").
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
    """Upsert every item in ``feed`` and prune anything published before the
    window opens. Idempotent for a given poll.
    """
    ensure_news_items_table(conn)
    cutoff = feed.fetched_at - timedelta(hours=feed.window_hours)
    for item in feed.items:
        conn.execute(
            f"""
            INSERT INTO {_TABLE}
                (dedupe_key, title, url, summary, source, published_at,
                 fetched_at, buckets, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                title = excluded.title,
                url = excluded.url,
                summary = excluded.summary,
                source = excluded.source,
                published_at = excluded.published_at,
                fetched_at = excluded.fetched_at,
                buckets = excluded.buckets,
                tags_json = excluded.tags_json
            """,
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
            ),
        )
    conn.execute(
        f"DELETE FROM {_TABLE} WHERE published_at < ?", (cutoff.isoformat(),)
    )
    conn.commit()


def load_cached_news(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    window_hours: int = 48,
) -> NewsFeed:
    """Rebuild a :class:`NewsFeed` from the cache, newest first, keeping only
    rows still inside ``window_hours`` of ``now``. The feed's ``fetched_at`` is
    the newest row's — the last time the window was refreshed.
    """
    ensure_news_items_table(conn)
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=window_hours)
    rows = conn.execute(
        f"""
        SELECT dedupe_key, title, url, summary, source, published_at,
               fetched_at, tags_json
        FROM {_TABLE}
        WHERE published_at >= ?
        ORDER BY published_at DESC, title COLLATE NOCASE DESC
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    items = tuple(_row_to_item(r) for r in rows)
    fetched_at = max((i.fetched_at for i in items), default=now)
    return NewsFeed(fetched_at=fetched_at, window_hours=window_hours, items=items)


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
        published_at=_parse(row[5]),
        fetched_at=_parse(row[6]),
        tags=tags,
        dedupe_key=row[0],
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
