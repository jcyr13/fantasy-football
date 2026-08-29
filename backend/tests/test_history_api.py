"""Issue #17 acceptance, end to end through the FastAPI test client: a week is
captured once as an immutable snapshot of projections / lineups /
recommendations / strategic outputs, a re-run does not overwrite it, and the
actual outcome is backfilled onto a separate record after games."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from weekly_fixtures import FixtureWeeklyDataSources


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(data_dir=tmp_path / "data"),
        weekly_sources=FixtureWeeklyDataSources(),
    )
    with TestClient(app) as c:
        yield c


def _capture(client: TestClient) -> dict:
    r = client.post("/api/history/capture")
    assert r.status_code == 200, r.text
    return r.json()


def test_history_is_empty_but_not_pending_before_any_capture(client: TestClient):
    body = client.get("/api/history").json()
    assert body["pending"] is False
    assert body["snapshots"] == []


def test_capture_freezes_the_four_screen_contracts(client: TestClient):
    body = _capture(client)
    assert body["created"] is True
    rec = body["record"]
    assert rec["snapshot_id"] == "2026-3"
    assert rec["season"] == 2026 and rec["week"] == 3
    assert rec["outcome"] is None

    captured = rec["captured"]
    assert set(captured) == {"weekly", "team_outlook", "trade_desk", "free_agents"}
    assert captured["weekly"]["week"] == 3
    assert len(captured["weekly"]["recommended_lineup"]) == 10
    # the Yahoo-set lineup is frozen alongside so the backfill can score it too
    assert len(captured["weekly"]["dead_parrots_current_lineup"]) == 10
    assert captured["team_outlook"]["signal"]["signal"] in {
        "contend", "rebuild", "hold", "too-early"
    }
    assert isinstance(captured["trade_desk"]["opportunity"], list)
    assert "rest_of_season" in captured["free_agents"]
    # the frozen rng_seed matches the assembled view's (ADR-0013 §5 / ADR-0014)
    assert rec["rng_seed"] == captured["weekly"]["rng_seed"]

    listed = client.get("/api/history").json()["snapshots"]
    assert [r["snapshot_id"] for r in listed] == ["2026-3"]


def test_recapture_for_the_same_week_never_overwrites_the_original(client: TestClient):
    first = _capture(client)["record"]
    again = client.post("/api/history/capture").json()

    assert again["created"] is False
    assert again["record"]["created_at"] == first["created_at"]
    assert again["record"]["captured"] == first["captured"]
    assert len(client.get("/api/history").json()["snapshots"]) == 1


def test_outcome_backfills_onto_a_separate_record_after_games(client: TestClient):
    rec = _capture(client)["record"]
    starters = [p["player_id"] for p in rec["captured"]["weekly"]["recommended_lineup"]]
    actuals = {pid: 10.0 + i for i, pid in enumerate(starters)}

    r = client.post(
        "/api/history/3/outcome",
        json={
            "dead_parrots_total": 140.5,
            "opponent_total": 128.0,
            "player_actuals": actuals,
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()["outcome"]
    assert out["result"] == "win"
    assert out["dead_parrots_total"] == 140.5
    # every recommended starter is scored; the Yahoo-set lineup may add more
    scored_ids = {p["player_id"] for p in out["player_actuals"]}
    assert set(starters) <= scored_ids
    one = out["player_actuals"][0]
    assert one["delta"] == pytest.approx(one["actual_points"] - one["projected_points"])

    # the immutable capture is unchanged by the backfill
    after = client.get("/api/history/3").json()
    assert after["captured"] == rec["captured"]
    assert after["outcome"]["result"] == "win"


def test_second_backfill_is_refused_with_409(client: TestClient):
    _capture(client)
    payload = {"dead_parrots_total": 100.0, "opponent_total": 90.0, "player_actuals": {}}
    assert client.post("/api/history/3/outcome", json=payload).status_code == 200

    dup = client.post(
        "/api/history/3/outcome",
        json={"dead_parrots_total": 1.0, "opponent_total": 999.0, "player_actuals": {}},
    )
    assert dup.status_code == 409
    # the first outcome stands
    assert client.get("/api/history/3").json()["outcome"]["result"] == "win"


def test_backfill_without_a_snapshot_is_404(client: TestClient):
    r = client.post(
        "/api/history/3/outcome",
        json={"dead_parrots_total": 1.0, "opponent_total": 2.0, "player_actuals": {}},
    )
    assert r.status_code == 404


def test_history_week_404_for_an_uncaptured_week(client: TestClient):
    _capture(client)
    assert client.get("/api/history/7").status_code == 404


def test_history_endpoints_still_answer_without_a_pull(tmp_path):
    # No weekly_sources: capture needs the assembled week (503), but reading the
    # empty history must still work.
    app = create_app(settings=Settings(data_dir=tmp_path / "data"))
    with TestClient(app) as c:
        assert c.get("/api/history").json() == {
            "pending": False,
            "reason": "",
            "snapshots": [],
        }
        assert c.post("/api/history/capture").status_code == 503
