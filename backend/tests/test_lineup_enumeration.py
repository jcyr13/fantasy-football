from __future__ import annotations

from itertools import combinations

from deadparrots.lineup import RIP_TIDE_SLOTS, enumerate_lineups, is_legal_lineup
from lineup_helpers import a_roster, rp

# Acceptance criterion 1: legal-lineup enumeration is provably complete and
# correct for a known test roster. The proof of record is the brute-force
# cross-check below — every 10-player subset that ``is_legal_lineup`` accepts,
# and no other, is produced exactly once.


def _brute_force_legal(players) -> set[frozenset[str]]:
    legal: set[frozenset[str]] = set()
    for combo in combinations(players, RIP_TIDE_SLOTS.size):
        if is_legal_lineup(list(combo), RIP_TIDE_SLOTS):
            legal.add(frozenset(p.player_id for p in combo))
    return legal


def test_enumeration_equals_brute_force_over_all_subsets():
    roster = a_roster(qb=2, rb=3, wr=3, te=2, k=1, def_=1, idp=1)  # 13 players
    enumerated = [lineup.player_ids for lineup in enumerate_lineups(roster)]

    assert len(enumerated) == len(set(enumerated))  # no lineup produced twice
    assert set(enumerated) == _brute_force_legal(roster)


def test_every_enumerated_lineup_is_legal_and_has_ten_players():
    roster = a_roster(qb=2, rb=4, wr=4, te=2, k=2, def_=2, idp=2)  # 18 players
    count = 0
    for lineup in enumerate_lineups(roster):
        count += 1
        assert len(lineup.players) == 10
        assert is_legal_lineup(list(lineup.players), RIP_TIDE_SLOTS)
    assert count == len(_brute_force_legal(roster))
    assert count > 0


def test_hand_computed_candidate_count_for_a_small_roster():
    # QB2 · RB3 · WR3 · TE2 · K1 · DEF1 · D1.
    #   flex=RB: C(3,3)·C(3,2)·C(2,1) = 1·3·2 = 6
    #   flex=WR: C(3,2)·C(3,3)·C(2,1) = 3·1·2 = 6
    #   flex=TE: C(3,2)·C(3,2)·C(2,2) = 3·3·1 = 9
    #   -> 21 flex-eligible sets · QB2 · K1 · DEF1 · D1 = 42
    roster = a_roster(qb=2, rb=3, wr=3, te=2, k=1, def_=1, idp=1)
    assert sum(1 for _ in enumerate_lineups(roster)) == 42


def test_a_roster_that_cannot_field_a_lineup_enumerates_nothing():
    no_kicker = a_roster(qb=2, rb=4, wr=4, te=2, k=0, def_=1, idp=1)
    assert list(enumerate_lineups(no_kicker)) == []


def test_a_te_can_occupy_the_flex():
    # RB2 · WR2 · TE2 is a legal role-count vector (flex = the extra TE), so a
    # roster with only two of every flex position still yields exactly one lineup.
    roster = [
        rp("qb", "QB", mean=20),
        rp("rb1", "RB", mean=14), rp("rb2", "RB", mean=13),
        rp("wr1", "WR", mean=15), rp("wr2", "WR", mean=14),
        rp("te1", "TE", mean=9), rp("te2", "TE", mean=8),
        rp("k", "K", mean=8),
        rp("def", "DEF", mean=7),
        rp("d", "IDP", mean=6),
    ]
    lineups = list(enumerate_lineups(roster))
    assert len(lineups) == 1
    assert lineups[0].player_ids == frozenset(p.player_id for p in roster)
