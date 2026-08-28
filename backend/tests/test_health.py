from __future__ import annotations


def test_health_reports_ok_when_stores_and_scheduler_are_up(client):
    resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["sqlite"] == "ok"
    assert body["duckdb"] == "ok"
    assert body["scheduler"] == "running"
    assert body["time"]


def test_startup_creates_the_sqlite_and_duckdb_files(client, data_dir):
    # The client fixture already entered the lifespan; the files should exist.
    client.get("/api/health")

    assert (data_dir / "app.sqlite").exists()
    assert (data_dir / "analytics.duckdb").exists()
