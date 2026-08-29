from __future__ import annotations

import json
from datetime import UTC, datetime

from deadparrots.yahoo.models import MatchupSnapshot, StandingsSnapshot
from deadparrots.yahoo.pages import ALL_PAGES, YahooPage
from deadparrots.yahoo.runner import run_yahoo_pull
from deadparrots.yahoo.status import recent_yahoo_pull_statuses

PULLED_AT = datetime(2026, 9, 22, 13, 0, 0, tzinfo=UTC)


def test_one_action_pulls_all_four_pages_archives_them_and_records_status(
    fake_yahoo_source, yahoo_raw_store, sqlite_conn
):
    run = run_yahoo_pull(
        source=fake_yahoo_source,
        raw_store=yahoo_raw_store,
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    assert run.ok
    assert run.pull_id == "20260922T130000Z"
    assert fake_yahoo_source.fetched == list(ALL_PAGES)

    # every raw payload retained as a timestamped file
    for page in ALL_PAGES:
        assert yahoo_raw_store.payload_path(run.pull_id, page).exists()
    manifest = json.loads(yahoo_raw_store.manifest_path(run.pull_id).read_text())
    assert manifest["source"] == "yahoo-fake"
    assert set(manifest["pages"]) == {p.value for p in ALL_PAGES}

    # normalized domain objects are on the run, typed
    assert isinstance(run.matchup, MatchupSnapshot)
    assert isinstance(run.standings, StandingsSnapshot)
    assert run.matchup.week == 3

    statuses = {s.page: s for s in recent_yahoo_pull_statuses(sqlite_conn)}
    assert set(statuses) == {p.value for p in ALL_PAGES}
    assert all(s.ok for s in statuses.values())
    assert statuses["matchup"].source == "yahoo:matchup"


def test_one_page_failure_is_isolated_and_never_alerts(
    make_fake_yahoo_source, yahoo_raw_store, sqlite_conn, caplog
):
    source = make_fake_yahoo_source(fail_for={YahooPage.INJURIES})

    run = run_yahoo_pull(
        source=source, raw_store=yahoo_raw_store, conn=sqlite_conn, pulled_at=PULLED_AT
    )

    assert not run.ok
    assert [r.page for r in run.failures] == [YahooPage.INJURIES]
    # the other three still landed and normalized
    assert run.matchup is not None
    assert run.free_agents is not None
    assert run.standings is not None
    assert run.injuries is None
    assert yahoo_raw_store.payload_path(run.pull_id, YahooPage.MATCHUP).exists()
    assert not yahoo_raw_store.payload_path(run.pull_id, YahooPage.INJURIES).exists()

    statuses = {s.page: s for s in recent_yahoo_pull_statuses(sqlite_conn)}
    assert statuses["injuries"].status == "failed"
    assert "simulated Yahoo scrape failure" in statuses["injuries"].error
    assert statuses["matchup"].ok

    # a failed page is logged, not escalated — no alerter is even a parameter here
    assert "1 failed page(s): injuries" in caplog.text


def test_standings_without_waiver_priority_flags_manual_entry_and_persists_it(
    make_fake_yahoo_source, yahoo_raw_store, sqlite_conn
):
    source = make_fake_yahoo_source(
        payload_names={YahooPage.STANDINGS: "standings_no_waiver"}
    )

    run = run_yahoo_pull(
        source=source, raw_store=yahoo_raw_store, conn=sqlite_conn, pulled_at=PULLED_AT
    )

    assert run.ok
    assert run.standings.waiver_priority_needs_manual_entry is True
    assert run.waiver_priority_needs_manual_entry is True
    # the flag outlives the run: it is written to the pull manifest
    manifest = yahoo_raw_store.load_manifest(run.pull_id)
    assert manifest["waiver_priority_needs_manual_entry"] is True
    assert yahoo_raw_store.latest_manifest()["waiver_priority_needs_manual_entry"] is True


def test_manifest_records_a_present_waiver_priority_column_as_not_needing_entry(
    fake_yahoo_source, yahoo_raw_store, sqlite_conn
):
    run = run_yahoo_pull(
        source=fake_yahoo_source,
        raw_store=yahoo_raw_store,
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    assert run.waiver_priority_needs_manual_entry is False
    assert yahoo_raw_store.load_manifest(run.pull_id)[
        "waiver_priority_needs_manual_entry"
    ] is False


def test_waiver_priority_flag_is_none_when_the_standings_page_failed(
    make_fake_yahoo_source, yahoo_raw_store, sqlite_conn
):
    source = make_fake_yahoo_source(fail_for={YahooPage.STANDINGS})

    run = run_yahoo_pull(
        source=source, raw_store=yahoo_raw_store, conn=sqlite_conn, pulled_at=PULLED_AT
    )

    assert run.waiver_priority_needs_manual_entry is None
    assert (
        yahoo_raw_store.load_manifest(run.pull_id)["waiver_priority_needs_manual_entry"]
        is None
    )


def test_rerun_in_the_same_second_starts_a_fresh_pull_set(
    fake_yahoo_source, yahoo_raw_store, sqlite_conn
):
    one = (YahooPage.MATCHUP,)
    first = run_yahoo_pull(
        source=fake_yahoo_source, raw_store=yahoo_raw_store, conn=sqlite_conn,
        pages=one, pulled_at=PULLED_AT,
    )
    second = run_yahoo_pull(
        source=fake_yahoo_source, raw_store=yahoo_raw_store, conn=sqlite_conn,
        pages=one, pulled_at=PULLED_AT,
    )

    assert first.ok and second.ok
    assert first.pull_id != second.pull_id
    assert yahoo_raw_store.payload_path(first.pull_id, YahooPage.MATCHUP).exists()
    assert yahoo_raw_store.payload_path(second.pull_id, YahooPage.MATCHUP).exists()
