from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deadparrots.news.cache import load_cached_news
from deadparrots.news.params import NewsParams
from deadparrots.news.raw import NewsPayloadFormat, RawNewsPayload
from deadparrots.news.runner import run_news_pull
from deadparrots.news.status import latest_pull_all_failed
from deadparrots.news.tagging import NewsTargets

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


class _EmptyEspnSource:
    """A feed that fetches fine but currently carries no articles."""

    source_label = "espn-api"

    def fetch(self) -> list[RawNewsPayload]:
        return [
            RawNewsPayload(
                source="espn-api",
                fmt=NewsPayloadFormat.ESPN_API_JSON,
                fetched_at=NOW,
                url="https://example.test/news/empty",
                body='{"articles": []}',
            )
        ]


def _sources(make_fake_news_source, *names, fail=()):
    out = []
    for name in names:
        out.append(
            make_fake_news_source(
                name, fail_with=RuntimeError("feed down") if name in fail else None
            )
        )
    return out


def test_pull_archives_every_feed_records_status_and_fills_the_cache(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    sources = _sources(
        make_fake_news_source, "espn_api_news", "espn_rss", "yahoo_rss"
    )
    run = run_news_pull(
        sources=sources,
        raw_store=news_raw_store,
        conn=sqlite_conn,
        targets=news_targets,
        now=NOW,
    )

    assert run.skipped is False
    assert run.ok is True
    assert {r.source for r in run.results} == {"espn-api", "espn-rss", "yahoo-rss"}
    assert all(r.ok for r in run.results)
    assert len(run.feed) == 7

    # raw payloads on disk + a manifest
    pull_dir = news_raw_store.pull_dir(run.pull_id)
    assert (pull_dir / "espn-api.json").exists()
    assert (pull_dir / "espn-rss.xml").exists()
    assert (pull_dir / "yahoo-rss.xml").exists()
    manifest = news_raw_store.load_manifest(run.pull_id)
    assert manifest["retained_items"] == 7
    assert {s["source"] for s in manifest["sources"]} == {
        "espn-api",
        "espn-rss",
        "yahoo-rss",
    }

    # the cache holds the same window
    cached = load_cached_news(sqlite_conn, now=NOW)
    assert len(cached) == 7
    assert cached.items[0].fetched_at == run.feed.fetched_at


def test_one_feed_failing_does_not_sink_the_others(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    sources = _sources(
        make_fake_news_source,
        "espn_api_news",
        "espn_rss",
        "yahoo_rss",
        fail=("yahoo_rss",),
    )
    run = run_news_pull(
        sources=sources,
        raw_store=news_raw_store,
        conn=sqlite_conn,
        targets=news_targets,
        now=NOW,
    )

    by_source = {r.source: r for r in run.results}
    assert by_source["yahoo-rss"].status == "failed"
    assert "feed down" in by_source["yahoo-rss"].error
    assert by_source["espn-api"].ok and by_source["espn-rss"].ok
    assert run.ok is False
    assert run.any_ok is True
    # Jaylen Warren only appears in the Yahoo feed, so he is not retained.
    assert not run.feed.for_player("Jaylen Warren")
    assert run.feed.for_player("Josh Allen")


def test_every_feed_failing_builds_an_empty_feed_and_flags_the_ticker_hidden(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    sources = _sources(
        make_fake_news_source,
        "espn_api_news",
        "espn_rss",
        fail=("espn_api_news", "espn_rss"),
    )
    run = run_news_pull(
        sources=sources,
        raw_store=news_raw_store,
        conn=sqlite_conn,
        targets=news_targets,
        now=NOW,
    )
    assert run.any_ok is False
    assert len(run.feed) == 0
    assert latest_pull_all_failed(sqlite_conn) is True


def test_the_poll_is_throttled_to_the_min_interval(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    params = NewsParams(min_poll_interval_minutes=30)

    def _pull(now):
        return run_news_pull(
            sources=_sources(make_fake_news_source, "espn_api_news"),
            raw_store=news_raw_store,
            conn=sqlite_conn,
            targets=news_targets,
            params=params,
            now=now,
        )

    first = _pull(NOW)
    assert first.skipped is False

    too_soon = _pull(NOW + timedelta(minutes=5))
    assert too_soon.skipped is True
    assert too_soon.feed is None
    # nothing new archived
    assert news_raw_store.pull_ids() == [first.pull_id]

    later = _pull(NOW + timedelta(minutes=31))
    assert later.skipped is False
    assert len(news_raw_store.pull_ids()) == 2


def test_throttle_can_be_disabled(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    kw = dict(raw_store=news_raw_store, conn=sqlite_conn, targets=news_targets)
    run_news_pull(sources=_sources(make_fake_news_source, "espn_api_news"), now=NOW, **kw)
    again = run_news_pull(
        sources=_sources(make_fake_news_source, "espn_api_news"),
        now=NOW + timedelta(minutes=1),
        throttle=False,
        **kw,
    )
    assert again.skipped is False


def test_a_total_failure_does_not_arm_the_throttle(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    kw = dict(raw_store=news_raw_store, conn=sqlite_conn, targets=news_targets)
    run_news_pull(
        sources=_sources(
            make_fake_news_source, "espn_api_news", fail=("espn_api_news",)
        ),
        now=NOW,
        **kw,
    )
    # 5 minutes later a retry is allowed because the first poll wrote no ok row
    retry = run_news_pull(
        sources=_sources(make_fake_news_source, "espn_api_news"),
        now=NOW + timedelta(minutes=5),
        **kw,
    )
    assert retry.skipped is False


def test_still_fresh_cached_items_are_carried_forward_when_a_feed_goes_quiet(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    kw = dict(raw_store=news_raw_store, conn=sqlite_conn, targets=news_targets)
    first = run_news_pull(
        sources=_sources(make_fake_news_source, "espn_api_news"), now=NOW, **kw
    )
    assert {i for i in first.feed.for_player("Josh Allen")}
    first_titles = {i.title for i in first.feed.items}

    # 31 minutes later the ESPN feed has scrolled and returns nothing new.
    later = run_news_pull(
        sources=[_EmptyEspnSource()], now=NOW + timedelta(minutes=31), **kw
    )
    assert {i.title for i in later.feed.items} == first_titles
    assert len(load_cached_news(sqlite_conn, now=NOW + timedelta(minutes=31))) == len(
        first_titles
    )


def test_a_target_change_drops_now_untagged_cached_items(
    make_fake_news_source, news_raw_store, sqlite_conn, news_targets
):
    kw = dict(raw_store=news_raw_store, conn=sqlite_conn)
    run_news_pull(
        sources=_sources(make_fake_news_source, "espn_api_news"),
        targets=news_targets,
        now=NOW,
        **kw,
    )
    # Next poll, Josh Allen and Rashee Rice are no longer targets.
    later = run_news_pull(
        sources=[_EmptyEspnSource()],
        targets=NewsTargets(my_roster=("Bijan Robinson",)),
        now=NOW + timedelta(minutes=31),
        **kw,
    )
    tagged = {t.player_name for i in later.feed.items for t in i.tags}
    assert tagged == {"Bijan Robinson"}


def test_empty_targets_still_archive_and_report_but_retain_nothing(
    make_fake_news_source, news_raw_store, sqlite_conn
):
    run = run_news_pull(
        sources=_sources(make_fake_news_source, "espn_api_news"),
        raw_store=news_raw_store,
        conn=sqlite_conn,
        targets=NewsTargets.empty(),
        now=NOW,
    )
    assert run.results[0].ok
    assert run.results[0].article_count == 5
    assert len(run.feed) == 0
    assert news_raw_store.load_manifest(run.pull_id)["targets_empty"] is True
