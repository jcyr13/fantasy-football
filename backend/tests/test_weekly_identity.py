"""Player identity resolution (issue #16; ADR-0013 §2)."""

from __future__ import annotations

from datetime import date

from deadparrots.weekly.identity import (
    PlayerResolver,
    normalize_name,
    slugify,
    synthetic_id,
)

ROSTER = [
    {
        "full_name": "Josh Allen",
        "team": "BUF",
        "position": "QB",
        "gsis_id": "00-0034857",
        "birth_date": "1996-05-21",
        "yahoo_id": "31215",
    },
    {
        "full_name": "Amon-Ra St. Brown",
        "team": "DET",
        "position": "WR",
        "gsis_id": "00-0036963",
        "birth_date": "1999-10-24",
    },
    {
        "full_name": "Michael Carter",
        "team": "ARI",
        "position": "RB",
        "gsis_id": "00-0036973",
    },
    {
        "full_name": "Michael Carter",
        "team": "NYJ",
        "position": "WR",
        "gsis_id": "00-0036500",
    },
]


def test_normalize_name_strips_punctuation_accents_and_suffix():
    assert normalize_name("Ja'Marr Chase Jr.") == "ja marr chase"
    assert normalize_name("Amon-Ra St. Brown") == "amon ra st brown"
    assert normalize_name("Kenneth Walker III") == "kenneth walker"


def test_resolves_by_full_name_and_team():
    r = PlayerResolver(ROSTER)
    hit = r.resolve("Amon-Ra St. Brown", team="DET", position="WR")
    assert hit is not None and hit.player_id == "00-0036963"
    assert hit.birth_date == date(1999, 10, 24)


def test_resolves_the_nflverse_initial_last_form():
    r = PlayerResolver(ROSTER)
    hit = r.resolve("J.Allen", team="BUF", position="QB")
    assert hit is not None and hit.player_id == "00-0034857"


def test_yahoo_id_wins_over_name():
    r = PlayerResolver(ROSTER)
    hit = r.resolve("Joshua Allen", team="XXX", position="QB", yahoo_id="31215")
    assert hit is not None and hit.player_id == "00-0034857"


def test_ambiguous_bare_name_needs_the_team():
    r = PlayerResolver(ROSTER)
    assert r.resolve("Michael Carter", position="RB") is None  # two of them
    got = r.resolve("Michael Carter", team="NYJ", position="WR")
    assert got is not None and got.player_id == "00-0036500"


def test_team_defense_resolves_to_the_abbreviation():
    r = PlayerResolver(ROSTER)
    hit = r.resolve("Cardinals", team="Ari", position="DEF")
    assert hit is not None and hit.player_id == "ARI" and hit.nfl_team == "ARI"


def test_unresolved_falls_back_to_a_synthetic_id():
    r = PlayerResolver(ROSTER)
    out = r.resolve_or_synthetic("Nobody At All", team="BUF", position="WR")
    assert out.resolved is False
    assert out.player_id == synthetic_id("Nobody At All") == "yahoo:nobody-at-all"


def test_slugify_and_synthetic_id_share_one_slug():
    assert slugify("Dead Parrots") == "dead-parrots"
    assert synthetic_id("Dead Parrots") == "yahoo:dead-parrots"
    assert synthetic_id("") == "yahoo:unknown"
