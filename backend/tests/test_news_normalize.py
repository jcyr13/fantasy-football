from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from deadparrots.news.normalize import (
    NewsNormalizationError,
    normalize_payload,
    normalize_payloads,
)

# recorded-payload-in -> normalized-articles-out (spec issue #15: "Source
# payload -> normalized items is covered by a recorded-payload test"). The HTTP
# fetch that produces the body is a separate seam and is not exercised here.


def test_espn_endpoint_payload_normalizes_every_linked_article(news_payload):
    articles = normalize_payload(news_payload("espn_api_news"))

    titles = [a.title for a in articles]
    # The wire item with no web/mobile link is dropped; everything else is kept
    # (the 48-hour window and player tagging run later, not in the parser).
    assert titles == [
        "Josh Allen (elbow) limited in practice Wednesday",
        "Bijan Robinson expected to see 20-plus touches vs. Saints",
        "Chiefs WR Rashee Rice suspended six games by NFL",
        "NFL Week 3 injury report roundup: every team's Wednesday status",
        "Patrick Mahomes throws four touchdowns in Chiefs rout",
    ]

    allen = articles[0]
    assert allen.url == "https://www.espn.com/nfl/story/_/id/1001/josh-allen-elbow-limited"
    assert allen.source == "espn-api"
    assert allen.published_at == datetime(2026, 9, 23, 11, 15, tzinfo=UTC)
    assert allen.summary and allen.summary.startswith("Buffalo Bills QB Josh Allen")


def test_rss_payload_normalizes_items_and_parses_rfc822_dates(news_payload):
    articles = normalize_payload(news_payload("espn_rss"))

    assert [a.title for a in articles] == [
        "Ja'Marr Chase catches two touchdowns in Bengals win",
        "Josh Allen (elbow) limited in practice Wednesday",
        "Tyreek Hill questionable with wrist injury",
        "Fantasy football Week 3 rankings: no player named here",
    ]
    chase = articles[0]
    assert chase.url == "https://www.espn.com/nfl/story/_/id/2001/jamarr-chase-two-tds"
    assert chase.source == "espn-rss"
    # "Mon, 22 Sep 2026 15:30:00 GMT" -> tz-aware UTC
    assert chase.published_at == datetime(2026, 9, 22, 15, 30, tzinfo=UTC)


def test_yahoo_rss_payload_normalizes(news_payload):
    articles = normalize_payload(news_payload("yahoo_rss"))
    assert {a.source for a in articles} == {"yahoo-rss"}
    assert [a.title for a in articles][0].startswith("Report: Jaylen Warren")


def test_normalize_payloads_concatenates_in_order(news_payload):
    combined = normalize_payloads(
        [news_payload("espn_api_news"), news_payload("espn_rss")]
    )
    assert len(combined) == 5 + 4
    assert {a.source for a in combined} == {"espn-api", "espn-rss"}


def test_a_body_that_is_not_json_is_rejected(news_payload):
    payload = replace(news_payload("espn_api_news"), body="<html>down for maintenance</html>")
    with pytest.raises(NewsNormalizationError) as excinfo:
        normalize_payload(payload)
    assert "not valid JSON" in str(excinfo.value)


def test_json_without_an_articles_array_is_rejected(news_payload):
    payload = replace(news_payload("espn_api_news"), body='{"header": "NFL News"}')
    with pytest.raises(NewsNormalizationError) as excinfo:
        normalize_payload(payload)
    assert "articles" in str(excinfo.value)


def test_a_body_that_is_not_xml_is_rejected(news_payload):
    payload = replace(news_payload("espn_rss"), body="not xml at all <<<")
    with pytest.raises(NewsNormalizationError) as excinfo:
        normalize_payload(payload)
    assert "not valid XML" in str(excinfo.value)


def test_xml_with_no_items_is_empty_not_an_error(news_payload):
    empty = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>ESPN</title></channel></rss>"
    )
    payload = replace(news_payload("espn_rss"), body=empty)
    assert normalize_payload(payload) == []
