from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.news.feed import build_news_feed
from deadparrots.news.normalize import ParsedArticle, normalize_payloads
from deadparrots.news.params import NewsParams
from deadparrots.news.tagging import NewsTargets

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _article(**kw) -> ParsedArticle:
    base = dict(
        title="Josh Allen throws four touchdowns",
        url="https://example.test/a",
        summary=None,
        source="espn-api",
        published_at=NOW - timedelta(hours=1),
    )
    base.update(kw)
    return ParsedArticle(**base)


def _all_fixture_articles(news_payload) -> list[ParsedArticle]:
    return normalize_payloads(
        [
            news_payload("espn_api_news"),
            news_payload("espn_rss"),
            news_payload("yahoo_rss"),
        ]
    )


def test_end_to_end_retains_only_fresh_tagged_deduped_items(news_payload, news_targets):
    feed = build_news_feed(
        _all_fixture_articles(news_payload), news_targets, now=NOW
    )

    # 7 retained: Josh Allen (merged), Rashee Rice, Bijan (yahoo), Tyreek Hill,
    # Bijan (espn), Ja'Marr Chase, Jaylen Warren — newest first.
    assert [i.title for i in feed.items] == [
        "Josh Allen (elbow) limited in practice Wednesday",
        "Chiefs WR Rashee Rice suspended six games by NFL",
        "Bijan Robinson leads all running backs in yards from scrimmage",
        "Tyreek Hill questionable with wrist injury",
        "Bijan Robinson expected to see 20-plus touches vs. Saints",
        "Ja'Marr Chase catches two touchdowns in Bengals win",
        "Report: Jaylen Warren to split backfield work in Pittsburgh",
    ]
    # Untagged league-wide items and the stale Mahomes recap are gone.
    assert not feed.for_player("Patrick Mahomes")
    assert feed.window_hours == 48
    assert feed.fetched_at == NOW


def test_the_same_story_from_two_feeds_collapses_to_one_item(news_payload, news_targets):
    feed = build_news_feed(
        _all_fixture_articles(news_payload), news_targets, now=NOW
    )
    allen = feed.for_player("Josh Allen")
    assert len(allen) == 1
    # http/https, www, and the ?ex_cid tracking param are normalized away.
    assert allen[0].source == "espn-api+espn-rss"
    # merged item takes the earliest publish time of the group
    assert allen[0].published_at == datetime(2026, 9, 23, 11, 15, tzinfo=UTC)


def test_items_outside_the_48h_window_are_dropped(news_targets):
    articles = [
        _article(title="Josh Allen fresh", published_at=NOW - timedelta(hours=47)),
        _article(title="Josh Allen stale", published_at=NOW - timedelta(hours=49)),
    ]
    feed = build_news_feed(articles, news_targets, now=NOW)
    assert [i.title for i in feed.items] == ["Josh Allen fresh"]


def test_future_dated_items_beyond_the_skew_tolerance_are_dropped(news_targets):
    params = NewsParams(future_skew_minutes=60)
    articles = [
        _article(title="Josh Allen soon", published_at=NOW + timedelta(minutes=30)),
        _article(title="Josh Allen bogus", published_at=NOW + timedelta(hours=6)),
    ]
    feed = build_news_feed(articles, news_targets, now=NOW, params=params)
    assert [i.title for i in feed.items] == ["Josh Allen soon"]


def test_untagged_items_are_never_retained(news_targets):
    feed = build_news_feed(
        [_article(title="NFL sets Week 3 flex schedule", url="https://example.test/x")],
        news_targets,
        now=NOW,
    )
    assert len(feed) == 0


def test_empty_targets_yield_an_empty_feed(news_payload):
    feed = build_news_feed(
        _all_fixture_articles(news_payload), NewsTargets.empty(), now=NOW
    )
    assert len(feed) == 0


def test_items_with_no_url_dedupe_on_normalized_title(news_targets):
    articles = [
        _article(title="Josh Allen (elbow)  LIMITED", url=""),
        _article(title="josh allen elbow limited", url="", source="yahoo-rss"),
    ]
    feed = build_news_feed(articles, news_targets, now=NOW)
    assert len(feed) == 1
    assert feed.items[0].source == "espn-api+yahoo-rss"


def test_fetched_at_overrides_now_for_the_stamp(news_targets):
    stamp = datetime(2026, 9, 23, 12, 5, tzinfo=UTC)
    feed = build_news_feed(
        [_article()], news_targets, now=NOW, fetched_at=stamp
    )
    assert feed.fetched_at == stamp
    assert feed.items[0].fetched_at == stamp
