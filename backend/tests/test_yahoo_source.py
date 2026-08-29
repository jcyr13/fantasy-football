from __future__ import annotations

from datetime import UTC, datetime

from deadparrots.yahoo.models import MatchupSnapshot
from deadparrots.yahoo.pages import ALL_PAGES, YahooPage
from deadparrots.yahoo.raw import YahooRawStore
from deadparrots.yahoo.runner import run_yahoo_pull
from deadparrots.yahoo.source import ReplayYahooSource, StaticYahooSource

# All Yahoo access goes through one interface; downstream code is source-agnostic
# (spec issue #7, acceptance criterion 2). The runner and normalizer are
# unchanged whether the payloads come from a scrape, an archived pull, or an
# in-memory capture.

PULLED_AT = datetime(2026, 9, 22, 13, 0, 0, tzinfo=UTC)


def test_replay_source_reruns_an_archived_pull_identically(
    fake_yahoo_source, tmp_path, sqlite_conn
):
    store = YahooRawStore(tmp_path / "data")
    first = run_yahoo_pull(
        source=fake_yahoo_source, raw_store=store, conn=sqlite_conn, pulled_at=PULLED_AT
    )

    replay = run_yahoo_pull(
        source=ReplayYahooSource(store, first.pull_id),
        raw_store=store,
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    assert replay.ok
    assert replay.pull_id != first.pull_id  # a fresh archive dir
    assert isinstance(replay.matchup, MatchupSnapshot)
    assert replay.matchup == first.matchup
    assert replay.standings.rows == first.standings.rows


def test_static_source_feeds_captured_bodies_through_the_same_pipeline(
    yahoo_payload, tmp_path, sqlite_conn
):
    bodies = {page: yahoo_payload(page).body for page in ALL_PAGES}
    source = StaticYahooSource(bodies)

    run = run_yahoo_pull(
        source=source,
        raw_store=YahooRawStore(tmp_path / "data"),
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    assert run.ok
    assert run.matchup.week == 3
    assert run.free_agents is not None


def test_replay_source_raises_for_a_page_absent_from_the_archive(
    make_fake_yahoo_source, tmp_path, sqlite_conn
):
    store = YahooRawStore(tmp_path / "data")
    partial = run_yahoo_pull(
        source=make_fake_yahoo_source(fail_for={YahooPage.STANDINGS}),
        raw_store=store,
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    replay = run_yahoo_pull(
        source=ReplayYahooSource(store, partial.pull_id),
        raw_store=store,
        conn=sqlite_conn,
        pulled_at=PULLED_AT,
    )

    assert [r.page for r in replay.failures] == [YahooPage.STANDINGS]
    assert "no archived standings payload" in replay.failures[0].error
