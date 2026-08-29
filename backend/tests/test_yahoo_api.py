from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings


@pytest.fixture
def pull_client(data_dir, fake_yahoo_source) -> Iterator[TestClient]:
    """A TestClient whose server has a fixture-backed assisted-pull source wired."""
    app = create_app(
        settings=Settings(data_dir=data_dir), yahoo_source=fake_yahoo_source
    )
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


def test_status_reports_a_reminder_before_any_pull_then_clears_after_one(pull_client):
    before = pull_client.get("/api/yahoo/status").json()
    assert before["last_successful_pull"] is None
    assert before["reminder"] is not None

    pull_client.post("/api/yahoo/pull")

    after = pull_client.get("/api/yahoo/status").json()
    assert after["last_successful_pull"] is not None
    assert after["reminder"] is None
    assert {p["page"] for p in after["pages"]} == {
        "matchup",
        "players",
        "injuries",
        "standings",
    }
