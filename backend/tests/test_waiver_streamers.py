from __future__ import annotations

import pytest

from deadparrots.waiver import streamer_options
from waiver_fixtures import a_state, fa, full_roster

# The streamer list (methodology §4.11): scoped to roles with a current
# bye/injury hole, ordered by next-week ceiling (P90), not rest-of-season
# value.


def _state_with_k_hole(**kw):
    # lone kicker and lone DEF on bye this week -> K and DEF are holes; every
    # other role is covered.
    roster = full_roster(k=1, def_=1, byes={"k1": 8, "def1": 8})
    return a_state(roster=roster, current_week=8, **kw)


def test_scoped_to_hole_roles_only():
    state = _state_with_k_hole(
        free_agents=[
            fa("k-a", "K", ros=60.0, ceiling=11.0),
            fa("def-a", "DEF", ros=80.0, ceiling=9.0),
            fa("wr-a", "WR", ros=200.0, ceiling=30.0),  # WR is not a hole
        ]
    )
    streamers = streamer_options(state)
    assert {s.role for s in streamers} == {"K", "DEF"}
    assert "wr-a" not in {s.player_id for s in streamers}


def test_ordered_by_next_week_ceiling_not_ros_value():
    state = _state_with_k_hole(
        free_agents=[
            fa("k-hold", "K", ros=90.0, ceiling=10.0),  # better ROS, lower ceiling
            fa("k-spike", "K", ros=50.0, ceiling=17.0),  # worse ROS, higher ceiling
        ]
    )
    streamers = streamer_options(state)
    assert [s.player_id for s in streamers] == ["k-spike", "k-hold"]
    assert [s.rank for s in streamers] == [1, 2]
    assert streamers[0].next_week_ceiling == pytest.approx(17.0)


def test_empty_when_no_current_hole():
    state = a_state(
        free_agents=[fa("k-a", "K", ros=60.0)],
        roster=full_roster(k=1),  # kicker healthy
        current_week=8,
    )
    assert streamer_options(state) == ()


def test_explicit_hole_roles_override_is_honoured():
    state = a_state(
        free_agents=[fa("wr-a", "WR", ros=120.0, ceiling=22.0)],
        roster=full_roster(),
        hole_roles=frozenset({"WR"}),
    )
    streamers = streamer_options(state)
    assert [s.player_id for s in streamers] == ["wr-a"]
    assert streamers[0].hole_role == "WR"


def test_entries_carry_the_three_annotations_and_reasons():
    state = _state_with_k_hole(
        free_agents=[fa("k-a", "K", ros=60.0, ceiling=11.0, bye_week=9)]
    )
    (s,) = streamer_options(state)
    assert s.need_fit.has_current_hole is True
    assert s.own_bye.bye_week == 9
    assert s.priority_verdict.verdict in {"worth-it", "marginal", "hold-priority"}
    assert any("P90" in r for r in s.reasons)
