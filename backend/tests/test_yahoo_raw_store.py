from __future__ import annotations

import json

import pytest

from deadparrots.yahoo.pages import YahooPage
from deadparrots.yahoo.raw import YahooArtifactExistsError, YahooRawStore

# Raw pull payloads are retained as timestamped files (spec issue #7, acceptance
# criterion 3).


def test_write_lands_a_timestamped_payload_under_data_yahoo(tmp_path, yahoo_payload):
    store = YahooRawStore(tmp_path / "data")

    path = store.write("20260922T130000Z", yahoo_payload(YahooPage.MATCHUP))

    assert path == tmp_path / "data" / "yahoo" / "20260922T130000Z" / "matchup.json"
    assert json.loads(path.read_text())["week"] == 3


def test_write_refuses_to_overwrite_an_existing_payload(tmp_path, yahoo_payload):
    store = YahooRawStore(tmp_path / "data")
    store.write("20260922T130000Z", yahoo_payload(YahooPage.STANDINGS))

    with pytest.raises(YahooArtifactExistsError):
        store.write("20260922T130000Z", yahoo_payload(YahooPage.STANDINGS))


def test_pull_ids_and_latest_payload_path_track_the_newest_pull(tmp_path, yahoo_payload):
    store = YahooRawStore(tmp_path / "data")
    store.write("20260901T120000Z", yahoo_payload(YahooPage.INJURIES))
    store.write("20260922T130000Z", yahoo_payload(YahooPage.INJURIES))

    assert store.pull_ids() == ["20260901T120000Z", "20260922T130000Z"]
    assert store.latest_payload_path(YahooPage.INJURIES).parent.name == "20260922T130000Z"
    assert store.latest_payload_path(YahooPage.MATCHUP) is None


def test_archived_payload_round_trips_through_load_payload(tmp_path, yahoo_payload):
    store = YahooRawStore(tmp_path / "data")
    original = yahoo_payload(YahooPage.PLAYERS)
    store.write("20260922T130000Z", original)

    reloaded = store.load_payload("20260922T130000Z", YahooPage.PLAYERS)

    assert reloaded is not None
    assert reloaded.page is YahooPage.PLAYERS
    assert reloaded.content_type == "application/json"
    assert json.loads(reloaded.body) == json.loads(original.body)


def test_write_manifest_records_the_run(tmp_path):
    store = YahooRawStore(tmp_path / "data")

    path = store.write_manifest("20260922T130000Z", {"pull_id": "20260922T130000Z", "week": 3})

    assert json.loads(path.read_text())["week"] == 3
