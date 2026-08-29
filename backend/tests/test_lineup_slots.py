from __future__ import annotations

import pytest

from deadparrots.lineup import (
    RIP_TIDE_SLOTS,
    assign_slots,
    can_field_legal_lineup,
    is_legal_lineup,
)
from lineup_helpers import rp

# The RIP TIDE starting slots: QB, 2×RB, 2×WR, TE, W/R/T flex, K, DEF, D.


def test_slots_field_ten_starters():
    assert RIP_TIDE_SLOTS.size == 10
    assert [rule.name for rule in RIP_TIDE_SLOTS.rules] == [
        "QB", "RB", "WR", "TE", "W/R/T", "K", "DEF", "D"
    ]


def test_role_count_distributions_are_the_three_flex_resolutions():
    dists = {
        tuple(sorted(d.items())) for d in RIP_TIDE_SLOTS.role_count_distributions()
    }
    assert dists == {
        (("DEF", 1), ("IDP", 1), ("K", 1), ("QB", 1), ("RB", 3), ("TE", 1), ("WR", 2)),
        (("DEF", 1), ("IDP", 1), ("K", 1), ("QB", 1), ("RB", 2), ("TE", 2), ("WR", 2)),
        (("DEF", 1), ("IDP", 1), ("K", 1), ("QB", 1), ("RB", 2), ("TE", 1), ("WR", 3)),
    }
    for dist in RIP_TIDE_SLOTS.role_count_distributions():
        assert sum(dist.values()) == 10


def _legal_ten(flex_position: str = "WR"):
    return [
        rp("qb", "QB", mean=20),
        rp("rb1", "RB", mean=14),
        rp("rb2", "RB", mean=12),
        rp("wr1", "WR", mean=15),
        rp("wr2", "WR", mean=13),
        rp("flex", flex_position, mean=11),
        rp("te", "TE", mean=9),
        rp("k", "K", mean=8),
        rp("def", "DEF", mean=7),
        rp("d", "IDP", mean=6),
    ]


def test_assign_slots_covers_every_slot_once_for_a_legal_lineup():
    assignment = assign_slots(_legal_ten(), RIP_TIDE_SLOTS)
    assert assignment is not None
    slot_names = [slot for slot, _ in assignment]
    assert slot_names == ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "K", "DEF", "D"]
    assert {player.player_id for _, player in assignment} == {
        "qb", "rb1", "rb2", "wr1", "wr2", "flex", "te", "k", "def", "d"
    }


@pytest.mark.parametrize("flex_position", ["WR", "RB", "TE"])
def test_flex_accepts_wr_rb_or_te(flex_position):
    assert is_legal_lineup(_legal_ten(flex_position), RIP_TIDE_SLOTS)


def test_flex_rejects_a_kicker():
    assert not is_legal_lineup(_legal_ten("K"), RIP_TIDE_SLOTS)


def test_wrong_player_count_is_never_legal():
    nine = _legal_ten()[:9]
    assert assign_slots(nine, RIP_TIDE_SLOTS) is None
    assert not is_legal_lineup(nine, RIP_TIDE_SLOTS)


def test_missing_a_required_role_is_illegal():
    # two team defenses, no individual defender -> the D slot cannot be filled
    lineup = _legal_ten()
    lineup[-1] = rp("def2", "DEF", mean=6)
    assert not is_legal_lineup(lineup, RIP_TIDE_SLOTS)


def test_too_many_of_one_role_beyond_any_distribution_is_illegal():
    # QB, 4×RB, 2×WR, TE, K, DEF -> 10 players but no legal role-count vector
    lineup = [
        rp("qb", "QB", mean=20),
        rp("rb1", "RB", mean=14),
        rp("rb2", "RB", mean=13),
        rp("rb3", "RB", mean=12),
        rp("rb4", "RB", mean=11),
        rp("wr1", "WR", mean=15),
        rp("wr2", "WR", mean=13),
        rp("te", "TE", mean=9),
        rp("k", "K", mean=8),
        rp("def", "DEF", mean=7),
    ]
    assert not is_legal_lineup(lineup, RIP_TIDE_SLOTS)


def test_can_field_legal_lineup_selects_from_a_larger_pool():
    # 12 players, two spare WRs: a legal ten can still be drawn out.
    pool = [*_legal_ten(), rp("wr3", "WR", mean=10), rp("wr4", "WR", mean=9)]
    assert can_field_legal_lineup(pool, RIP_TIDE_SLOTS)


def test_can_field_legal_lineup_false_when_a_role_is_unreachable():
    # No individual defender anywhere in the pool -> the D slot can never fill.
    pool = [p for p in _legal_ten() if p.position != "IDP"]
    pool.append(rp("def2", "DEF", mean=5))
    pool.append(rp("wr3", "WR", mean=10))
    assert not can_field_legal_lineup(pool, RIP_TIDE_SLOTS)


def test_can_field_legal_lineup_false_when_the_pool_is_too_small():
    assert not can_field_legal_lineup(_legal_ten()[:9], RIP_TIDE_SLOTS)
