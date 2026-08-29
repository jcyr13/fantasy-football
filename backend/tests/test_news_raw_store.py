from __future__ import annotations

import pytest

from deadparrots.news.raw import NewsArtifactExistsError, NewsPayloadFormat


def test_write_archives_a_payload_by_source_and_extension(news_raw_store, news_payload):
    payload = news_payload("espn_api_news")
    path = news_raw_store.write("20260923T120000Z", payload)

    assert path.name == "espn-api.json"
    assert path.read_text(encoding="utf-8") == payload.body


def test_write_refuses_to_clobber(news_raw_store, news_payload):
    payload = news_payload("espn_rss")
    news_raw_store.write("20260923T120000Z", payload)
    with pytest.raises(NewsArtifactExistsError):
        news_raw_store.write("20260923T120000Z", payload)


def test_manifest_round_trips_and_load_payloads_replays(news_raw_store, news_payload):
    pull_id = "20260923T120000Z"
    for name in ("espn_api_news", "espn_rss", "yahoo_rss"):
        news_raw_store.write(pull_id, news_payload(name))
    news_raw_store.write_manifest(
        pull_id,
        {
            "pull_id": pull_id,
            "sources": [
                {"source": "espn-api", "fmt": "espn-api-json", "url": "u1"},
                {"source": "espn-rss", "fmt": "rss", "url": "u2"},
                {"source": "yahoo-rss", "fmt": "rss", "url": "u3"},
            ],
        },
    )

    replayed = news_raw_store.load_payloads(pull_id)
    assert [p.source for p in replayed] == ["espn-api", "espn-rss", "yahoo-rss"]
    assert replayed[0].fmt is NewsPayloadFormat.ESPN_API_JSON
    assert replayed[1].fmt is NewsPayloadFormat.RSS
    assert replayed[0].body == news_payload("espn_api_news").body


def test_pull_ids_are_chronological_and_latest_manifest_wins(news_raw_store, news_payload):
    news_raw_store.write("20260923T120000Z", news_payload("espn_api_news"))
    news_raw_store.write_manifest("20260923T120000Z", {"retained_items": 1})
    news_raw_store.write("20260923T123000Z", news_payload("espn_api_news"))
    news_raw_store.write_manifest("20260923T123000Z", {"retained_items": 9})

    assert news_raw_store.pull_ids() == ["20260923T120000Z", "20260923T123000Z"]
    assert news_raw_store.latest_manifest()["retained_items"] == 9
