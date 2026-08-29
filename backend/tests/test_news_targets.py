from __future__ import annotations

from deadparrots.news.targets import targets_from_latest_yahoo_pull
from deadparrots.yahoo.pages import YahooPage


def test_no_yahoo_pull_yet_yields_empty_targets(yahoo_raw_store):
    targets = targets_from_latest_yahoo_pull(yahoo_raw_store)
    assert targets.is_empty()


def test_targets_come_from_the_latest_matchup_pull(yahoo_raw_store, yahoo_payload):
    yahoo_raw_store.write("20260922T130000Z", yahoo_payload(YahooPage.MATCHUP))

    targets = targets_from_latest_yahoo_pull(yahoo_raw_store)

    assert "Josh Allen" in targets.my_roster
    assert "Bijan Robinson" in targets.my_roster
    assert "Ja'Marr Chase" in targets.my_roster
    # opponent roster populated, free-agent shortlist deferred to issue #16
    assert targets.opponent
    assert targets.free_agents == ()


def test_a_newer_pull_without_a_matchup_page_falls_back_to_the_older_one(
    yahoo_raw_store, yahoo_payload
):
    yahoo_raw_store.write("20260922T130000Z", yahoo_payload(YahooPage.MATCHUP))
    yahoo_raw_store.write("20260923T130000Z", yahoo_payload(YahooPage.STANDINGS))

    targets = targets_from_latest_yahoo_pull(yahoo_raw_store)
    assert "Josh Allen" in targets.my_roster
