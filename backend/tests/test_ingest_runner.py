from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from deadparrots.ingest.cache import NflverseParquetCache
from deadparrots.ingest.datasets import DATASETS_BY_NAME
from deadparrots.ingest.runner import run_nflverse_pull
from deadparrots.ingest.status import recent_pull_statuses

PULLED_AT = datetime(2026, 8, 28, 12, 30, 0, tzinfo=UTC)
THREE = (
    DATASETS_BY_NAME["pbp"],
    DATASETS_BY_NAME["schedules"],
    DATASETS_BY_NAME["idp"],
)


@pytest.fixture
def cache(tmp_path) -> NflverseParquetCache:
    return NflverseParquetCache(tmp_path / "data")


def test_successful_run_writes_parquet_records_status_and_sends_no_alert(
    cache, sqlite_conn, fake_source, recording_alerter
):
    run = run_nflverse_pull(
        source=fake_source,
        cache=cache,
        conn=sqlite_conn,
        alerter=recording_alerter,
        datasets=THREE,
        pulled_at=PULLED_AT,
    )

    assert run.ok
    assert run.pull_id == "20260828T123000Z"
    assert fake_source.loaded == ["pbp", "schedules", "idp"]
    for name in ("pbp", "schedules", "idp"):
        assert cache.parquet_path(run.pull_id, name).exists()

    statuses = {s.dataset: s for s in recent_pull_statuses(sqlite_conn)}
    assert set(statuses) == {"pbp", "schedules", "idp"}
    assert all(s.ok and s.row_count and s.row_count > 0 for s in statuses.values())
    assert recording_alerter.messages == []


def test_one_dataset_failure_is_isolated_and_triggers_a_single_email_alert(
    cache, sqlite_conn, recording_alerter, make_fake_source
):
    source = make_fake_source(fail_for={"schedules"})

    run = run_nflverse_pull(
        source=source,
        cache=cache,
        conn=sqlite_conn,
        alerter=recording_alerter,
        datasets=THREE,
        pulled_at=PULLED_AT,
    )

    assert not run.ok
    assert [r.dataset for r in run.failures] == ["schedules"]
    # the other two still landed
    assert cache.parquet_path(run.pull_id, "pbp").exists()
    assert cache.parquet_path(run.pull_id, "idp").exists()
    assert not cache.parquet_path(run.pull_id, "schedules").exists()

    statuses = {s.dataset: s for s in recent_pull_statuses(sqlite_conn)}
    assert statuses["schedules"].status == "failed"
    assert "simulated nflverse outage" in statuses["schedules"].error
    assert statuses["pbp"].ok

    assert len(recording_alerter.messages) == 1
    subject, body = recording_alerter.messages[0]
    assert "1 dataset(s) failed" in subject
    assert "schedules" in body


def test_run_refreshes_duckdb_views_when_a_connection_is_supplied(
    cache, sqlite_conn, fake_source, recording_alerter
):
    conn = duckdb.connect()

    run = run_nflverse_pull(
        source=fake_source,
        cache=cache,
        conn=sqlite_conn,
        alerter=recording_alerter,
        datasets=THREE,
        duckdb_conn=conn,
        pulled_at=PULLED_AT,
    )

    count = conn.execute("SELECT count(*) FROM nflverse_pbp").fetchone()[0]
    assert count == next(r.row_count for r in run.results if r.dataset == "pbp")


def test_rerunning_in_the_same_second_starts_a_fresh_pull_set_without_alerting(
    cache, sqlite_conn, fake_source, recording_alerter
):
    one = (DATASETS_BY_NAME["pbp"],)
    first = run_nflverse_pull(
        source=fake_source, cache=cache, conn=sqlite_conn, alerter=recording_alerter,
        datasets=one, pulled_at=PULLED_AT,
    )
    second = run_nflverse_pull(
        source=fake_source, cache=cache, conn=sqlite_conn, alerter=recording_alerter,
        datasets=one, pulled_at=PULLED_AT,
    )

    assert first.ok and second.ok
    assert first.pull_id != second.pull_id  # bumped to the next free second
    assert cache.parquet_path(first.pull_id, "pbp").exists()
    assert cache.parquet_path(second.pull_id, "pbp").exists()
    assert recording_alerter.messages == []
