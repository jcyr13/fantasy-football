from __future__ import annotations

import pytest

from deadparrots.waiver import rest_of_season_value
from waiver_fixtures import a_state, fa, full_roster

# The rest-of-season list (methodology §4.10): ordered by value over
# replacement at position — projected ROS points minus the best *other* free
# agent at the role.


def test_ordered_by_value_over_replacement_not_raw_points():
    # Raw ROS points would rank the QB (200) first. But replacement QB is deep
    # (190), so the QB's value over replacement is only +10; the RB (150) sits
    # over a 120 replacement for +30 and leads.
    state = a_state(
        free_agents=[
            fa("qb-hi", "QB", ros=200.0),
            fa("qb-repl", "QB", ros=190.0),
            fa("rb-hi", "RB", ros=150.0),
            fa("rb-repl", "RB", ros=120.0),
        ]
    )
    ros = rest_of_season_value(state)

    assert [r.player_id for r in ros] == ["rb-hi", "qb-hi", "qb-repl", "rb-repl"]
    assert ros[0].value_over_replacement == pytest.approx(30.0)
    assert ros[1].value_over_replacement == pytest.approx(10.0)
    # the replacement-level players are measured against the one above them
    assert ros[2].value_over_replacement == pytest.approx(-10.0)
    assert ros[3].value_over_replacement == pytest.approx(-30.0)


def test_replacement_is_the_best_other_free_agent_at_the_role():
    state = a_state(
        free_agents=[
            fa("wr-1", "WR", ros=100.0),
            fa("wr-2", "WR", ros=80.0),
            fa("wr-3", "WR", ros=60.0),
        ]
    )
    ros = {r.player_id: r for r in rest_of_season_value(state)}

    # best WR is measured against the runner-up (80)
    assert ros["wr-1"].replacement.from_player_id == "wr-2"
    assert ros["wr-1"].value_over_replacement == pytest.approx(20.0)
    # everyone else is measured against the best (100)
    assert ros["wr-2"].replacement.from_player_id == "wr-1"
    assert ros["wr-3"].replacement.from_player_id == "wr-1"
    assert ros["wr-3"].value_over_replacement == pytest.approx(-40.0)


def test_solo_free_agent_at_a_role_has_zero_value_over_replacement():
    state = a_state(free_agents=[fa("k-solo", "K", ros=70.0)])
    (row,) = rest_of_season_value(state)

    assert row.value_over_replacement == pytest.approx(0.0)
    assert row.replacement.from_player_id == "k-solo"
    assert any("Only free agent at K" in r for r in row.reasons)


def test_positional_rank_is_within_role():
    state = a_state(
        free_agents=[
            fa("wr-1", "WR", ros=100.0),
            fa("rb-1", "RB", ros=95.0),
            fa("wr-2", "WR", ros=50.0),
            fa("rb-2", "RB", ros=48.0),
        ]
    )
    ros = {r.player_id: r for r in rest_of_season_value(state)}
    assert (ros["wr-1"].positional_rank, ros["wr-2"].positional_rank) == (1, 2)
    assert (ros["rb-1"].positional_rank, ros["rb-2"].positional_rank) == (1, 2)
    assert {r.rank for r in ros.values()} == {1, 2, 3, 4}


def test_every_entry_carries_the_three_annotations():
    state = a_state(
        free_agents=[fa("wr-1", "WR", ros=100.0, bye_week=11), fa("wr-2", "WR", ros=70.0)],
        roster=full_roster(),
    )
    for row in rest_of_season_value(state):
        assert row.need_fit.role == row.role
        assert row.own_bye is not None
        assert row.priority_verdict.verdict in {"worth-it", "marginal", "hold-priority"}
        assert len(row.reasons) == 4
