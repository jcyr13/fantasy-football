from __future__ import annotations

import json
from dataclasses import replace

import pytest

from deadparrots.yahoo.models import (
    FreeAgentListing,
    InjuryReport,
    MatchupSnapshot,
    StandingsSnapshot,
)
from deadparrots.yahoo.normalize import YahooNormalizationError, normalize
from deadparrots.yahoo.pages import YahooPage

# recorded-payload-in -> normalized-objects-out (spec issue #7, acceptance
# criterion 4). One test per page against the committed fixtures.


def test_matchup_payload_normalizes_to_both_full_rosters(yahoo_payload):
    snapshot = normalize(yahoo_payload(YahooPage.MATCHUP))

    assert isinstance(snapshot, MatchupSnapshot)
    assert snapshot.week == 3
    assert snapshot.dead_parrots.is_dead_parrots is True
    assert snapshot.dead_parrots.team_name == "Dead Parrots"
    assert snapshot.opponent.team_name == "Norwegian Blues"
    assert snapshot.opponent.is_dead_parrots is False

    # 10 starting slots (QB/2WR/2RB/TE/flex/K/DEF/D), 5 bench, 2 IR.
    assert len(snapshot.dead_parrots.entries) == 17
    assert len(snapshot.dead_parrots.starters) == 10
    assert {e.slot for e in snapshot.dead_parrots.bench} == {"BN", "IR"}

    allen = snapshot.dead_parrots.starters[0]
    assert (allen.player_name, allen.nfl_team, allen.position) == ("Josh Allen", "Buf", "QB")
    assert allen.yahoo_projected_points == 23.8

    waddle = next(e for e in snapshot.dead_parrots.entries if e.player_name == "Jaylen Waddle")
    assert waddle.injury_status == "Q"

    mccaffrey = next(
        e for e in snapshot.dead_parrots.entries if e.player_name == "Christian McCaffrey"
    )
    assert mccaffrey.is_starter is False
    assert mccaffrey.yahoo_projected_points is None  # Yahoo renders "-" for an IR player


def test_matchup_projected_total_sums_only_the_starters(yahoo_payload):
    snapshot = normalize(yahoo_payload(YahooPage.MATCHUP))

    assert snapshot.dead_parrots.yahoo_projected_total == pytest.approx(131.7)
    assert snapshot.opponent.yahoo_projected_total == pytest.approx(136.6)


def test_players_payload_normalizes_free_agents_and_waiver_rows(yahoo_payload):
    listing = normalize(yahoo_payload(YahooPage.PLAYERS))

    assert isinstance(listing, FreeAgentListing)
    by_name = {p.player_name: p for p in listing.players}

    jennings = by_name["Jauan Jennings"]
    assert jennings.availability == "FA"
    assert jennings.percent_rostered == 61.0
    assert jennings.yahoo_projected_points == 12.4

    tracy = by_name["Tyrone Tracy Jr."]
    assert tracy.availability == "W"
    assert tracy.waiver_claim_date == "Wed"

    mims = by_name["Marvin Mims Jr."]
    assert mims.percent_rostered is None  # blank "%" cell
    assert mims.yahoo_projected_points is None


def test_injuries_payload_normalizes_every_row(yahoo_payload):
    report = normalize(yahoo_payload(YahooPage.INJURIES))

    assert isinstance(report, InjuryReport)
    assert len(report.entries) == 6
    waddle = next(e for e in report.entries if e.player_name == "Jaylen Waddle")
    assert waddle.status == "Questionable"
    assert waddle.detail == "Shoulder"
    mcbride = next(e for e in report.entries if e.player_name == "Trey McBride")
    assert mcbride.detail is None


def test_standings_payload_with_waiver_priority_is_sourced_from_standings(yahoo_payload):
    snapshot = normalize(yahoo_payload(YahooPage.STANDINGS))

    assert isinstance(snapshot, StandingsSnapshot)
    assert len(snapshot.rows) == 12
    assert snapshot.waiver_priority_source == "standings"
    assert snapshot.waiver_priority_needs_manual_entry is False

    parrots = next(r for r in snapshot.rows if r.team_name == "Dead Parrots")
    assert (parrots.wins, parrots.losses, parrots.ties) == (2, 1, 0)
    assert parrots.points_for == 351.1
    assert parrots.division == "RIP"
    assert parrots.waiver_priority == 11

    last = next(r for r in snapshot.rows if r.team_name == "Fish Slappers")
    assert last.waiver_priority == 1  # reverse-standings queue


def test_standings_without_waiver_priority_is_flagged_for_manual_entry(yahoo_payload):
    snapshot = normalize(yahoo_payload(YahooPage.STANDINGS, "standings_no_waiver"))

    assert snapshot.waiver_priority_source == "manual-entry-required"
    assert snapshot.waiver_priority_needs_manual_entry is True
    assert all(r.waiver_priority is None for r in snapshot.rows)
    # everything else on the page still normalizes
    assert len(snapshot.rows) == 12
    assert snapshot.rows[0].team_name == "Norwegian Blues"


def test_missing_required_field_raises_normalization_error(yahoo_payload):
    payload = yahoo_payload(YahooPage.MATCHUP)
    broken = json.loads(payload.body)
    del broken["week"]
    payload = replace(payload, body=json.dumps(broken))

    with pytest.raises(YahooNormalizationError) as excinfo:
        normalize(payload)
    assert "week" in str(excinfo.value)
    assert excinfo.value.page == "matchup"


def test_matchup_without_a_dead_parrots_flag_is_rejected(yahoo_payload):
    payload = yahoo_payload(YahooPage.MATCHUP)
    broken = json.loads(payload.body)
    for team in broken["teams"]:
        team["is_dead_parrots"] = False
    payload = replace(payload, body=json.dumps(broken))

    with pytest.raises(YahooNormalizationError):
        normalize(payload)
