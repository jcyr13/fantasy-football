from __future__ import annotations

import json
from datetime import UTC, datetime

from deadparrots.consensus.models import ConsensusFeed
from deadparrots.consensus.runner import run_consensus_pull
from deadparrots.consensus.sources import FallbackConsensusSource
from deadparrots.consensus.status import recent_consensus_pull_statuses

PULLED_AT = datetime(2026, 9, 9, 11, 0, 0, tzinfo=UTC)


def test_successful_pull_archives_payload_normalizes_and_records_status(
    fake_consensus_source, consensus_raw_store, sqlite_conn
):
    run = run_consensus_pull(
        source=fake_consensus_source,
        raw_store=consensus_raw_store,
        conn=sqlite_conn,
        season=2026,
        week=1,
        pulled_at=PULLED_AT,
    )

    assert run.ok
    assert run.pull_id == "20260909T110000Z"
    assert fake_consensus_source.calls == [(2026, 1)]
    assert isinstance(run.feed, ConsensusFeed)
    assert len(run.feed) == 7

    # raw payload retained as a timestamped file + a manifest for the run
    assert consensus_raw_store.payload_path(run.pull_id).exists()
    manifest = json.loads(consensus_raw_store.manifest_path(run.pull_id).read_text())
    assert manifest["source"] == "ffanalytics"
    assert manifest["projection_count"] == 7
    assert manifest["week"] == 1

    statuses = recent_consensus_pull_statuses(sqlite_conn)
    assert len(statuses) == 1
    assert statuses[0].ok
    assert statuses[0].source == "ffanalytics"
    assert statuses[0].projection_count == 7
    assert statuses[0].week == 1


def test_a_fetch_failure_is_recorded_and_never_raises(
    make_fake_consensus_source, consensus_raw_store, sqlite_conn, caplog
):
    source = make_fake_consensus_source(fail_with=RuntimeError("sidecar drop missing"))

    run = run_consensus_pull(
        source=source,
        raw_store=consensus_raw_store,
        conn=sqlite_conn,
        season=2026,
        week=1,
        pulled_at=PULLED_AT,
    )

    assert not run.ok
    assert run.feed is None
    assert not consensus_raw_store.payload_path(run.pull_id).exists()

    statuses = recent_consensus_pull_statuses(sqlite_conn)
    assert statuses[0].status == "failed"
    assert "sidecar drop missing" in statuses[0].error
    # a failed consensus pull is logged, not escalated (no alerter parameter here)
    assert "consensus pull" in caplog.text.lower()
    manifest = consensus_raw_store.load_manifest(run.pull_id)
    assert manifest["status"] == "failed"


def test_fallback_source_uses_sleeper_when_the_sidecar_drop_is_unavailable(
    make_fake_consensus_source, consensus_raw_store, sqlite_conn
):
    sidecar = make_fake_consensus_source(fail_with=FileNotFoundError("no ffanalytics drop"))
    sleeper = make_fake_consensus_source("sleeper_week1")
    source = FallbackConsensusSource([sidecar, sleeper])

    run = run_consensus_pull(
        source=source,
        raw_store=consensus_raw_store,
        conn=sqlite_conn,
        season=2026,
        week=1,
        pulled_at=PULLED_AT,
    )

    assert run.ok
    assert run.feed.source == "sleeper"
    assert recent_consensus_pull_statuses(sqlite_conn)[0].source == "sleeper"


def test_rerun_in_the_same_second_starts_a_fresh_pull_set(
    fake_consensus_source, consensus_raw_store, sqlite_conn
):
    first = run_consensus_pull(
        source=fake_consensus_source, raw_store=consensus_raw_store, conn=sqlite_conn,
        season=2026, week=1, pulled_at=PULLED_AT,
    )
    second = run_consensus_pull(
        source=fake_consensus_source, raw_store=consensus_raw_store, conn=sqlite_conn,
        season=2026, week=1, pulled_at=PULLED_AT,
    )

    assert first.ok and second.ok
    assert first.pull_id != second.pull_id
    assert consensus_raw_store.payload_path(first.pull_id).exists()
    assert consensus_raw_store.payload_path(second.pull_id).exists()
