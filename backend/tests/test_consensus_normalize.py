from __future__ import annotations

import json
from dataclasses import replace

import pytest

from deadparrots.consensus.models import ConsensusFeed
from deadparrots.consensus.normalize import ConsensusNormalizationError, normalize
from deadparrots.scoring import ScoringUnit

# recorded-payload-in -> normalized-objects-out (spec issue #8, acceptance
# criterion 4). The normalized projection's ``projection`` must equal the RIP
# TIDE points the *validated* scoring engine assigns to the mapped stat line —
# these expected numbers are computed by hand from RIP_TIDE_RULESET.


def test_ffanalytics_payload_normalizes_and_rescores_every_position(consensus_payload):
    feed = normalize(consensus_payload("ffanalytics_week1"))

    assert isinstance(feed, ConsensusFeed)
    assert feed.source == "ffanalytics"
    assert (feed.season, feed.week) == (2026, 1)
    assert len(feed) == 7

    scored = {p.player_name: p for p in feed.projections}

    # QB: 265/25 + 1.8*6 - 0.6 - 2.1 + 34/10 + 0.45*6 + 0.1*2  (fumble_lost = 0.0)
    allen = scored["Josh Allen"]
    assert allen.unit is ScoringUnit.OFFENSE
    assert allen.gsis_id == "00-0034857"
    assert allen.projection == pytest.approx(25.0)
    assert allen.source_points == 22.4
    assert "rec" not in allen.scored_stats  # PPR receptions are not a RIP TIDE stat

    # RB: 92/10 + 0.62*6 + 30/10 + 0.18*6
    assert scored["Bijan Robinson"].projection == pytest.approx(17.0)

    # TE: 58/10 + 0.45*6
    assert scored["Trey McBride"].projection == pytest.approx(8.5)

    # K: distance-tiered FGs + PATs - short miss - PAT miss
    assert scored["Harrison Butker"].unit is ScoringUnit.KICKER
    assert scored["Harrison Butker"].projection == pytest.approx(11.15)

    # team DEF: events + return yards + points-allowed tier for 19.4 (<=20 -> +1)
    niners = scored["San Francisco 49ers"]
    assert niners.unit is ScoringUnit.TEAM_DEFENSE
    assert niners.projection == pytest.approx(13.78)

    # IDP / D slot: solo 1 / assist 0.5 / sack 2 / INT 2 / PD 1 / TFL 1 / ...
    warner = scored["Fred Warner"]
    assert warner.unit is ScoringUnit.INDIVIDUAL_DEFENSE
    assert warner.projection == pytest.approx(10.54)

    # WR: 88/10 + 0.6*6 + 4/10 ; the PPR "rec" key is not a RIP TIDE stat
    assert scored["Ja'Marr Chase"].projection == pytest.approx(12.8)


def test_a_projection_is_a_scored_mean_not_a_distribution(consensus_payload):
    feed = normalize(consensus_payload("ffanalytics_week1"))
    allen = feed.get("Josh Allen")

    # the consensus feed supplies "the consensus number" (a mean); floor / ceiling
    # shape is the model's job (methodology §3.1, docs/adr/0005)
    assert not hasattr(allen, "floor")
    assert not hasattr(allen, "ceiling")
    assert set(allen.scored_stats) == {
        "passing_yards",
        "passing_touchdowns",
        "interceptions_thrown",
        "sacks_taken",
        "rushing_yards",
        "rushing_touchdowns",
        "fumbles_lost",
        "two_point_conversions",
    }


def test_sleeper_stopgap_payload_normalizes_through_the_same_path(consensus_payload):
    feed = normalize(consensus_payload("sleeper_week1"))

    assert feed.source == "sleeper"
    scored = {p.player_name: p for p in feed.projections}

    # QB: 230/25 + 1.5*6 - 0.5 - 1.8 + 45/10 + 0.7*6 + 0.1*2
    hurts = scored["Jalen Hurts"]
    assert hurts.unit is ScoringUnit.OFFENSE
    assert hurts.sleeper_id == "6904"
    assert hurts.projection == pytest.approx(24.8)

    # team DEF: pts_allow 24 lands in the <=27 tier (0.0)
    cowboys = scored["Dallas Cowboys"]
    assert cowboys.unit is ScoringUnit.TEAM_DEFENSE
    assert cowboys.projection == pytest.approx(14.1)


def test_unknown_source_is_rejected(consensus_payload):
    payload = consensus_payload("ffanalytics_week1")
    broken = json.loads(payload.body)
    broken["source"] = "fantasypros"
    payload = replace(payload, body=json.dumps(broken), source="fantasypros")

    with pytest.raises(ConsensusNormalizationError) as excinfo:
        normalize(payload)
    assert "stat-key map" in str(excinfo.value)


def test_players_in_positions_the_league_never_rosters_are_dropped(consensus_payload):
    payload = consensus_payload("ffanalytics_week1")
    data = json.loads(payload.body)
    data["players"].append(
        {"name": "Some Lineman", "team": "BUF", "position": "OL", "stats": {"pass_yds": 0}}
    )
    data["players"][3]["position"] = "P"  # was the TE — a punter has no scoring surface
    payload = replace(payload, body=json.dumps(data))

    feed = normalize(payload)

    names = {p.player_name for p in feed.projections}
    assert "Some Lineman" not in names
    assert "Trey McBride" not in names  # dropped: reassigned to P
    assert len(feed) == 6


def test_missing_required_envelope_field_is_rejected(consensus_payload):
    payload = consensus_payload("ffanalytics_week1")
    broken = json.loads(payload.body)
    del broken["week"]
    payload = replace(payload, body=json.dumps(broken))

    with pytest.raises(ConsensusNormalizationError) as excinfo:
        normalize(payload)
    assert "week" in str(excinfo.value)


def test_a_feed_whose_stat_keys_no_longer_map_fails_loudly(consensus_payload):
    payload = consensus_payload("ffanalytics_week1")
    broken = json.loads(payload.body)
    for player in broken["players"]:
        player["stats"] = {"totally_renamed_key": 12.3}
    payload = replace(payload, body=json.dumps(broken))

    with pytest.raises(ConsensusNormalizationError) as excinfo:
        normalize(payload)
    assert "stat-key map is stale" in str(excinfo.value)


def test_a_partial_rename_of_one_unit_still_fails_loudly(consensus_payload):
    # only the kicker's keys drift: offense/DEF/IDP still score, but a silently
    # zero-point kicker is exactly what the guard must catch.
    payload = consensus_payload("ffanalytics_week1")
    broken = json.loads(payload.body)
    for player in broken["players"]:
        if player["position"] == "K":
            player["stats"] = {"fg_made_short": 1.0, "extra_points": 2.0}
    payload = replace(payload, body=json.dumps(broken))

    with pytest.raises(ConsensusNormalizationError) as excinfo:
        normalize(payload)
    assert "kicker" in str(excinfo.value)


def test_helpers_select_by_unit_and_position(consensus_payload):
    feed = normalize(consensus_payload("ffanalytics_week1"))

    assert {p.player_name for p in feed.for_unit(ScoringUnit.OFFENSE)} == {
        "Josh Allen",
        "Bijan Robinson",
        "Ja'Marr Chase",
        "Trey McBride",
    }
    assert [p.player_name for p in feed.for_position("k")] == ["Harrison Butker"]
    assert set(feed.by_entity_id()) >= {"00-0034857", "00-0038542"}
