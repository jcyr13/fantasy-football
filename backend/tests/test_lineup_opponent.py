from __future__ import annotations

import pytest

from deadparrots.lineup import build_opponent_lineup, is_legal_lineup
from lineup_helpers import rp

# Acceptance criterion 6: the opponent lineup falls back to the heuristic when no
# set lineup exists, and the assumption used is exposed.


def _opp_roster(**overrides) -> list:
    """A 16-player opponent roster: 2 QB, 4 RB, 4 WR, 2 TE, 1 K, 1 DEF, 2 D.
    ``overrides`` maps a player_id to ``dict(available=False)`` etc."""
    base = [
        rp("o-qb1", "QB", mean=18.0), rp("o-qb2", "QB", mean=10.0),
        rp("o-rb1", "RB", mean=14.0), rp("o-rb2", "RB", mean=12.0),
        rp("o-rb3", "RB", mean=9.0), rp("o-rb4", "RB", mean=7.0),
        rp("o-wr1", "WR", mean=15.0), rp("o-wr2", "WR", mean=13.0),
        rp("o-wr3", "WR", mean=11.0), rp("o-wr4", "WR", mean=6.0),
        rp("o-te1", "TE", mean=9.0), rp("o-te2", "TE", mean=5.0),
        rp("o-k1", "K", mean=8.0),
        rp("o-def1", "DEF", mean=7.0),
        rp("o-d1", "IDP", mean=6.0), rp("o-d2", "IDP", mean=4.0),
    ]
    if overrides:
        base = [
            rp(
                p.player_id, p.position,
                mean=p.sim.mean,
                available=overrides.get(p.player_id, {}).get("available", p.available),
            )
            for p in base
        ]
    return base


SET_TEN = [
    "o-qb1", "o-rb1", "o-rb2", "o-wr1", "o-wr2", "o-wr3",
    "o-te1", "o-k1", "o-def1", "o-d1",
]


def test_uses_the_yahoo_set_lineup_when_it_is_complete_and_legal():
    result = build_opponent_lineup(_opp_roster(), yahoo_starters=SET_TEN)
    assert result.assumption == "yahoo-set"
    assert result.player_ids == frozenset(SET_TEN)
    assert is_legal_lineup(list(result.players))


def test_falls_back_when_a_yahoo_set_starter_is_unavailable():
    roster = _opp_roster(**{"o-wr3": {"available": False}})
    result = build_opponent_lineup(
        roster, yahoo_starters=SET_TEN, prior_week_starters=SET_TEN
    )
    assert result.assumption == "prior-week-heuristic"
    assert "o-wr3" not in result.player_ids
    assert is_legal_lineup(list(result.players))
    joined = " ".join(result.notes)
    assert "o-wr3" in joined and "unavailable" in joined
    assert any("Filled an open slot" in n for n in result.notes)


def test_falls_back_when_the_yahoo_set_lineup_is_illegal():
    illegal = ["o-qb1", "o-qb2", *SET_TEN[2:]]  # two QBs, no flex-legal shape
    result = build_opponent_lineup(_opp_roster(), yahoo_starters=illegal)
    assert result.assumption == "projection-heuristic"
    assert any("incomplete, illegal" in n for n in result.notes)


def test_prior_week_heuristic_applies_an_obvious_bench_upgrade():
    # last week started the weak o-rb4; o-rb2 (a far better back) sat on the bench
    prior = [
        "o-qb1", "o-rb1", "o-rb4", "o-wr1", "o-wr2", "o-wr3",
        "o-te1", "o-k1", "o-def1", "o-d1",
    ]
    result = build_opponent_lineup(_opp_roster(), prior_week_starters=prior)
    assert result.assumption == "prior-week-heuristic"
    assert "o-rb2" in result.player_ids
    assert "o-rb4" not in result.player_ids
    assert any("Obvious upgrade" in n for n in result.notes)


def test_obvious_upgrade_pass_is_capped():
    # last week started four punt-level players; the bench is stacked. Without a
    # cap the heuristic would rebuild the whole lineup; it must stop at the cap.
    prior = [
        "o-qb2", "o-rb3", "o-rb4", "o-wr3", "o-wr4", "o-te2",
        "o-te1", "o-k1", "o-def1", "o-d2",
    ]
    result = build_opponent_lineup(
        _opp_roster(), prior_week_starters=prior, max_obvious_upgrades=1
    )
    assert result.assumption == "prior-week-heuristic"
    assert sum("Obvious upgrade" in n for n in result.notes) == 1


def test_projection_heuristic_when_there_is_no_set_or_prior_lineup():
    result = build_opponent_lineup(_opp_roster())
    assert result.assumption == "projection-heuristic"
    assert is_legal_lineup(list(result.players))
    assert any("fallback" in n.lower() for n in result.notes)
    # highest-projected legal lineup: the strong QB starts, the punt-level WR sits
    assert "o-qb1" in result.player_ids
    assert "o-wr4" not in result.player_ids


def test_incomplete_yahoo_lineup_is_flagged_and_falls_back():
    result = build_opponent_lineup(_opp_roster(), yahoo_starters=SET_TEN[:8])
    assert result.assumption == "projection-heuristic"
    assert any("incomplete" in n for n in result.notes)


def test_prior_week_starter_no_longer_rostered_is_noted_and_replaced():
    prior = ["gone-player", *SET_TEN[1:]]
    result = build_opponent_lineup(_opp_roster(), prior_week_starters=prior)
    assert result.assumption == "prior-week-heuristic"
    assert is_legal_lineup(list(result.players))
    assert any("no longer on the roster" in n for n in result.notes)


def test_raises_when_no_legal_lineup_can_be_built_at_all():
    thin = [
        rp("o-qb1", "QB", mean=18.0),
        rp("o-rb1", "RB", mean=14.0), rp("o-rb2", "RB", mean=12.0),
        rp("o-wr1", "WR", mean=15.0), rp("o-wr2", "WR", mean=13.0),
        rp("o-te1", "TE", mean=9.0),
        rp("o-k1", "K", mean=8.0),
        rp("o-def1", "DEF", mean=7.0),
        # no IDP
    ]
    with pytest.raises(ValueError):
        build_opponent_lineup(thin)
