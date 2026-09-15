from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.yahoo.pages import YahooPage
from deadparrots.yahoo.raw import YahooRawStore


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


def _cache_schedule(test_client: TestClient, rows: list[tuple[int, int, str]]) -> None:
    """Stand in for a cached nflverse schedule on the server's DuckDB."""
    conn = test_client.app.state.duckdb
    conn.execute(
        "CREATE TABLE nflverse_schedules "
        "(season INTEGER, week INTEGER, gameday VARCHAR, game_type VARCHAR)"
    )
    conn.executemany(
        "INSERT INTO nflverse_schedules VALUES (?, ?, ?, 'REG')", rows
    )


def _latest_manifest_week(data_dir: Path) -> int | None:
    return YahooRawStore(data_dir).latest_manifest()["week"]


def test_post_pull_targets_the_current_week_from_the_cached_schedule(
    pull_client, fake_yahoo_source, data_dir
):
    today = date.today()
    _cache_schedule(
        pull_client,
        [
            (2026, 1, (today - timedelta(days=1)).isoformat()),  # week 1 final
            (2026, 2, (today + timedelta(days=3)).isoformat()),
        ],
    )

    assert pull_client.post("/api/yahoo/pull").status_code == 200

    assert set(fake_yahoo_source.weeks) == {2}
    assert _latest_manifest_week(data_dir) == 2


def test_post_pull_without_a_cached_schedule_uses_yahoos_default_week(
    pull_client, fake_yahoo_source, data_dir
):
    assert pull_client.post("/api/yahoo/pull").json()["ok"] is True

    assert set(fake_yahoo_source.weeks) == {None}
    assert _latest_manifest_week(data_dir) is None


def test_post_pull_week_query_overrides_the_computed_week(
    pull_client, fake_yahoo_source, data_dir
):
    _cache_schedule(pull_client, [(2026, 2, (date.today() + timedelta(days=3)).isoformat())])

    assert pull_client.post("/api/yahoo/pull?week=5").status_code == 200

    assert set(fake_yahoo_source.weeks) == {5}
    assert _latest_manifest_week(data_dir) == 5


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
