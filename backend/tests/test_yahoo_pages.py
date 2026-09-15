from __future__ import annotations

from deadparrots.yahoo.pages import YahooPage, page_path

# The URL each scraped page is read from. Standings is the odd one out:
# /f1/<id>/standings is Yahoo's "Live Standings" head-to-head grid with no
# W-L-T table; the real standings table is on the league home page (issue #52).


def test_pages_live_under_the_league():
    assert page_path(YahooPage.MATCHUP) == "/f1/735806/matchup"
    assert page_path(YahooPage.PLAYERS) == "/f1/735806/players"
    assert page_path(YahooPage.INJURIES) == "/f1/735806/injuries"


def test_standings_are_read_from_the_league_home_standings_tab():
    assert page_path(YahooPage.STANDINGS) == "/f1/735806?lhst=stand"


def test_week_is_only_appended_to_the_matchup_page():
    assert page_path(YahooPage.MATCHUP, week=3) == "/f1/735806/matchup?week=3"
    assert page_path(YahooPage.STANDINGS, week=3) == "/f1/735806?lhst=stand"
