from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.yahoo.pages import YahooPage


@pytest.fixture
def pull_client(data_dir, fake_yahoo_source) -> Iterator[TestClient]:
    """A TestClient whose server has a fixture-backed assisted-pull source wired."""
    app = create_app(
        settings=Settings(data_dir=data_dir), yahoo_source=fake_yahoo_source
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def no_waiver_pull_client(data_dir, make_fake_yahoo_source) -> Iterator[TestClient]:
    """As ``pull_client``, but the standings page carries no waiver-priority column."""
    source = make_fake_yahoo_source(
        payload_names={YahooPage.STANDINGS: "standings_no_waiver"}
    )
    app = create_app(settings=Settings(data_dir=data_dir), yahoo_source=source)
    with TestClient(app) as test_client:
        yield test_client


def test_post_pull_runs_the_assisted_pull_and_reports_every_page(pull_client):
    resp = pull_client.post("/api/yahoo/pull")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert {p["page"] for p in body["pages"]} == {"matchup", "players", "injuries", "standings"}
    assert all(p["status"] == "ok" for p in body["pages"])
    assert body["waiver_priority_needs_manual_entry"] is False


def test_post_pull_is_503_when_no_source_is_configured(client):
    resp = client.post("/api/yahoo/pull")

    assert resp.status_code == 503
    assert "source" in resp.json()["detail"].lower()


def test_missing_waiver_priority_is_flagged_and_persists_to_the_status_endpoint(
    no_waiver_pull_client,
):
    pulled = no_waiver_pull_client.post("/api/yahoo/pull").json()
    assert pulled["waiver_priority_needs_manual_entry"] is True

    # the flag survives the POST response — the freshness endpoint still reports it
    status = no_waiver_pull_client.get("/api/yahoo/status").json()
    assert status["waiver_priority_needs_manual_entry"] is True


def test_status_reports_a_reminder_before_any_pull_then_clears_after_one(pull_client):
    before = pull_client.get("/api/yahoo/status").json()
    assert before["last_successful_pull"] is None
    assert before["reminder"] is not None

    pull_client.post("/api/yahoo/pull")

    after = pull_client.get("/api/yahoo/status").json()
    assert after["last_successful_pull"] is not None
    assert after["reminder"] is None
    assert after["waiver_priority_needs_manual_entry"] is False
    assert {p["page"] for p in after["pages"]} == {
        "matchup",
        "players",
        "injuries",
        "standings",
    }
