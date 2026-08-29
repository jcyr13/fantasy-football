from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.news.cache import load_cached_news, replace_cached_news
from deadparrots.news.models import NewsBucket, NewsFeed, NewsItem, PlayerTag

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _item(key: str, *, hours_ago: float, bucket: NewsBucket, fetched_at=NOW) -> NewsItem:
    return NewsItem(
        title=f"story {key}",
        url=f"https://example.test/{key}",
        summary="blurb",
        source="espn-api",
        published_at=NOW - timedelta(hours=hours_ago),
        fetched_at=fetched_at,
        tags=(PlayerTag(player_name="Josh Allen", bucket=bucket, matched_text="josh allen"),),
        dedupe_key=f"url:{key}",
    )


def _feed(items, *, fetched_at=NOW, window_hours=48) -> NewsFeed:
    return NewsFeed(fetched_at=fetched_at, window_hours=window_hours, items=tuple(items))


def test_round_trips_items_and_tags(sqlite_conn):
    feed = _feed(
        [
            _item("a", hours_ago=1, bucket=NewsBucket.MY_ROSTER),
            _item("b", hours_ago=5, bucket=NewsBucket.FREE_AGENT),
        ]
    )
    replace_cached_news(sqlite_conn, feed)

    loaded = load_cached_news(sqlite_conn, now=NOW)
    assert [i.dedupe_key for i in loaded.items] == ["url:a", "url:b"]  # newest first
    assert loaded.items[0].tags[0].bucket is NewsBucket.MY_ROSTER
    assert loaded.items[1].tags[0].bucket is NewsBucket.FREE_AGENT
    assert loaded.items[0].source == "espn-api"


def test_replace_is_idempotent_and_upserts_by_dedupe_key(sqlite_conn):
    replace_cached_news(sqlite_conn, _feed([_item("a", hours_ago=1, bucket=NewsBucket.MY_ROSTER)]))
    replace_cached_news(sqlite_conn, _feed([_item("a", hours_ago=1, bucket=NewsBucket.OPPONENT)]))

    loaded = load_cached_news(sqlite_conn, now=NOW)
    assert len(loaded.items) == 1
    assert loaded.items[0].tags[0].bucket is NewsBucket.OPPONENT


def test_replace_prunes_rows_that_fell_out_of_the_window(sqlite_conn):
    replace_cached_news(
        sqlite_conn, _feed([_item("old", hours_ago=1, bucket=NewsBucket.MY_ROSTER)])
    )
    # Two days later the old row is outside a 48h window and the new poll drops it.
    later = NOW + timedelta(days=2)
    replace_cached_news(
        sqlite_conn,
        _feed(
            [
                NewsItem(
                    title="fresh",
                    url="https://example.test/fresh",
                    summary=None,
                    source="espn-api",
                    published_at=later - timedelta(hours=2),
                    fetched_at=later,
                    tags=(
                        PlayerTag(
                            player_name="Josh Allen",
                            bucket=NewsBucket.MY_ROSTER,
                            matched_text="josh allen",
                        ),
                    ),
                    dedupe_key="url:fresh",
                )
            ],
            fetched_at=later,
        ),
    )

    keys = {i.dedupe_key for i in load_cached_news(sqlite_conn, now=later).items}
    assert keys == {"url:fresh"}


def test_load_filters_by_window_on_read(sqlite_conn):
    replace_cached_news(
        sqlite_conn,
        _feed(
            [
                _item("recent", hours_ago=10, bucket=NewsBucket.MY_ROSTER),
                _item("edge", hours_ago=47, bucket=NewsBucket.MY_ROSTER),
            ]
        ),
    )
    # Read from a point where "edge" is now 51h old.
    loaded = load_cached_news(sqlite_conn, now=NOW + timedelta(hours=4), window_hours=48)
    assert [i.dedupe_key for i in loaded.items] == ["url:recent"]


def test_load_on_empty_cache_returns_an_empty_feed(sqlite_conn):
    loaded = load_cached_news(sqlite_conn, now=NOW)
    assert len(loaded) == 0
    assert loaded.fetched_at == NOW
