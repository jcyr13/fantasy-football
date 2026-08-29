"""Issue #16 acceptance: ingestion fixtures → scoring → projection → simulation
→ endpoint JSON, driven through the FastAPI test client (ADR-0013 §5)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deadparrots.api.ops import RefreshOutcome
from deadparrots.app import create_app
from deadparrots.config import Settings
from weekly_fixtures import FixtureWeeklyDataSources


class _FakeRefreshRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def refresh(self, sources) -> list[RefreshOutcome]:
        names = tuple(sources)
        self.calls.append(names)
        return [RefreshOutcome(n, True, f"refreshed {n}") for n in names]


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(data_dir=tmp_path / "data"),
        weekly_sources=FixtureWeeklyDataSources(),
        refresh_runner=_FakeRefreshRunner(),
    )
    with TestClient(app) as c:
        yield c


def test_weekly_view_endpoint_full_contract(client: TestClient):
    r = client.get("/api/weekly")
    assert r.status_code == 200
    body = r.json()

    assert body["season"] == 2026
    assert body["week"] == 3
    assert body["dead_parrots_team"] == "Dead Parrots"
    assert body["opponent_team"] == "Spanish Inquisition"
    assert body["opponent_assumption"] == "yahoo-set"
    assert len(body["opponent_likely_lineup"]) == 10
    assert len(body["recommended_lineup"]) == 10
    assert len(body["gap_drivers"]) == 10
    assert len(body["swing_players"]) == 10
    assert {n["label"] for n in body["named_lineups"]} == {
        "max_p_win", "max_ev", "floor", "ceiling"
    }
    for side in ("dead_parrots_totals", "opponent_totals"):
        t = body[side]
        assert t["floor"] <= t["projection"] <= t["ceiling"]
        assert t["yahoo_projected_total"] is not None
    assert 0.0 <= body["win_probability"] <= 1.0
    assert isinstance(body["favored"], bool)
    assert body["caveats"]  # v1 approximations are disclosed


def test_weekly_view_rng_seed_stable_across_reloads(client: TestClient):
    a = client.get("/api/weekly").json()
    b = client.get("/api/weekly").json()
    assert a["rng_seed"] == b["rng_seed"]
    assert a["win_probability"] == b["win_probability"]
    assert a["recommended_lineup"] == b["recommended_lineup"]


def test_threshold_rule_toggle_switches_the_recommendation(client: TestClient):
    default = client.get("/api/weekly").json()
    toggled = client.get("/api/weekly", params={"engine": "threshold-rule"}).json()
    assert default["recommendation_engine"] == "max-p-win"
    assert toggled["recommendation_engine"] == "threshold-rule"
    assert client.get("/api/weekly", params={"engine": "nonsense"}).status_code == 422


def test_current_lineup_totals_are_reported_alongside_the_recommendation(client):
    body = client.get("/api/weekly").json()
    # The fixture's Dead Parrots Yahoo-set lineup is a legal 10, so its totals
    # and win% come back next to the recommended lineup's.
    cur = body["dead_parrots_current_totals"]
    assert cur is not None
    assert cur["floor"] <= cur["projection"] <= cur["ceiling"]
    assert 0.0 <= body["current_win_probability"] <= 1.0
    assert isinstance(body["recommended_lineup_is_current"], bool)


def test_lineup_lab_compute_and_illegal_marking(client: TestClient):
    auto = client.get("/api/weekly/lineup-lab/auto")
    assert auto.status_code == 200
    legal_ids = auto.json()["max_p_win"]
    assert len(legal_ids) == 10

    ok = client.post("/api/weekly/lineup-lab", json={"starter_ids": legal_ids})
    assert ok.status_code == 200
    ok_body = ok.json()
    assert ok_body["legal"] is True
    assert ok_body["reason"] is None
    assert ok_body["floor"] <= ok_body["total"] <= ok_body["ceiling"] + 1e-6
    assert 0.0 <= ok_body["win_probability"] <= 1.0
    assert ok_body["caveats"]  # the numbers rest on the §3 baseline; disclosed

    on_ir = client.post(
        "/api/weekly/lineup-lab",
        json={"starter_ids": legal_ids, "ir_ids": [legal_ids[0]]},
    ).json()
    assert on_ir["legal"] is False
    assert "IR" in on_ir["reason"]

    bad = client.post(
        "/api/weekly/lineup-lab", json={"starter_ids": legal_ids[:8]}
    ).json()
    assert bad["legal"] is False
    assert "10 players" in bad["reason"]

    two_qbs = client.post(
        "/api/weekly/lineup-lab",
        json={"starter_ids": [*legal_ids[:9], _second_qb(auto.json())]},
    ).json()
    assert two_qbs["legal"] is False
    assert two_qbs["reason"]


def _second_qb(auto_body: dict) -> str:
    qbs = [p["player_id"] for p in auto_body["roster"] if p["position"] == "QB"]
    return qbs[-1]


def test_free_agents_endpoint(client: TestClient):
    body = client.get("/api/free-agents").json()
    assert body["week"] == 3
    assert body["waiver_priority"]["current_priority"] == 11
    assert body["waiver_priority"]["team_count"] == 12
    assert "window_name" in body["cutdown_window"]
    assert isinstance(body["rest_of_season"], list)
    assert isinstance(body["streamers"], list)
    for fa in body["rest_of_season"]:
        assert {"player_id", "name", "position", "ros_projected_points",
                "priority_verdict"} <= fa.keys()


def test_team_outlook_endpoint(client: TestClient):
    body = client.get("/api/team-outlook").json()
    assert body["week"] == 3
    assert 0.0 <= body["team_strength"]["percentile"] <= 100.0
    assert 0.0 <= body["playoff_odds"] <= 1.0
    assert body["signal"]["signal"] in {"contend", "rebuild", "hold", "too-early"}
    assert body["signal"]["recommends_transaction"] is False
    assert isinstance(body["bye_crunch"], list)
    assert body["caveats"]


def test_trade_desk_endpoint(client: TestClient):
    body = client.get("/api/trade-desk").json()
    assert body["week"] == 3
    assert body["countdown"]["target_date"] == "2026-11-28"
    assert isinstance(body["opportunity"], list) and body["opportunity"]
    assert isinstance(body["buy_low"], list)
    assert isinstance(body["sell_high"], list)
    assert isinstance(body["desperate_teams"], list)


def test_news_and_history_and_freshness(client: TestClient):
    news = client.get("/api/news").json()
    assert news["items"] == []
    assert news["all_sources_failed"] is False

    hist = client.get("/api/history").json()
    assert hist["pending"] is True
    assert hist["snapshots"] == []

    fresh = client.get("/api/freshness").json()
    names = {s["source"] for s in fresh["sources"]}
    assert names == {"nflverse", "consensus", "news", "yahoo"}
    for s in fresh["sources"]:
        assert s["state"] in {"ok", "failed", "never"}


def test_refresh_triggers(client: TestClient):
    allr = client.post("/api/refresh").json()
    assert {o["source"] for o in allr["outcomes"]} == {"nflverse", "consensus", "news"}
    assert all(o["ok"] for o in allr["outcomes"])

    one = client.post("/api/refresh/news").json()
    assert [o["source"] for o in one["outcomes"]] == ["news"]

    missing = client.post("/api/refresh/bogus")
    assert missing.status_code == 404


def test_weekly_endpoints_503_without_a_pull(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path / "data2"))
    with TestClient(app) as c:
        assert c.get("/api/weekly").status_code == 503
        assert c.get("/api/team-outlook").status_code == 503
