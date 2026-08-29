from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from deadparrots.waiver import waiver_wire
from waiver_fixtures import a_state, fa, full_roster

# Issue #14 acceptance criterion 6: fed a hand-built fixture league state, both
# list orderings assert correctly. One coherent fixture drives the whole layer.


def _hand_built_state():
    # Dead Parrots roster: lone kicker on bye in Week 8 (a current K hole), and
    # two of four RB starters share a Week 11 bye (an RB bye crunch ahead).
    roster = full_roster(
        qb=2, rb=4, wr=4, te=2, k=1, def_=1, idp=1,
        byes={"k1": 8, "rb1": 11, "rb2": 11},
    )

    free_agents = [
        # --- RB: replacement level 100, so the ordering is by the gap ------
        fa("rb-stud", "RB", ros=140.0, ceiling=15.0, bye_week=9),   # +40 over repl
        fa("rb-repl", "RB", ros=100.0, ceiling=12.0),               # the replacement
        fa("rb-depth", "RB", ros=88.0, ceiling=9.0),                # -12
        # --- WR: higher raw points, thinner edge -----------------------
        fa("wr-hi", "WR", ros=150.0, ceiling=20.0),                 # +15 over repl
        fa("wr-repl", "WR", ros=135.0, ceiling=18.0),
        # --- K: the current hole; streamer-relevant --------------------
        fa("k-ceiling", "K", ros=55.0, ceiling=13.0),               # low ROS, top ceiling
        fa("k-hold", "K", ros=78.0, ceiling=8.0),                   # best ROS K, low ceiling
    ]
    return a_state(
        free_agents=free_agents,
        roster=roster,
        current_week=8,
        waiver_priority=3,
        regular_season_weeks=14,
    )


def test_rest_of_season_list_is_ordered_by_value_over_replacement():
    wire = waiver_wire(_hand_built_state())
    ros = wire.rest_of_season

    # rb-stud (+40) > wr-hi (+15) > k-hold (+23 vs k-ceiling... check below)
    # explicit: value over replacement per role, best other FA at role.
    vor = {r.player_id: r.value_over_replacement for r in ros}
    assert vor["rb-stud"] == pytest.approx(40.0)   # 140 - best other RB (100)
    assert vor["wr-hi"] == pytest.approx(15.0)     # 150 - best other WR (135)
    assert vor["k-hold"] == pytest.approx(23.0)    # 78 - best other K (55)
    assert vor["rb-depth"] == pytest.approx(-52.0)  # 88 - best other RB (rb-stud, 140)

    # the list is sorted by descending value over replacement
    values = [r.value_over_replacement for r in ros]
    assert values == sorted(values, reverse=True)
    assert [r.player_id for r in ros[:3]] == ["rb-stud", "k-hold", "wr-hi"]
    assert [r.player_id for r in ros[-2:]] == ["rb-repl", "rb-depth"]
    assert [r.rank for r in ros] == list(range(1, len(ros) + 1))


def test_streamer_list_is_ordered_by_next_week_ceiling_and_scoped_to_the_hole():
    wire = waiver_wire(_hand_built_state())

    assert wire.hole_roles == ("K",)  # only the lone kicker's bye
    assert [s.player_id for s in wire.streamers] == ["k-ceiling", "k-hold"]
    assert [s.next_week_ceiling for s in wire.streamers] == [13.0, 8.0]
    assert all(s.role == "K" for s in wire.streamers)


def test_entries_are_annotated_with_fit_bye_and_priority_verdict():
    wire = waiver_wire(_hand_built_state())
    stud = next(r for r in wire.rest_of_season if r.player_id == "rb-stud")

    # bench-need fit carries the Week 11 RB bye crunch
    assert stud.need_fit.bye_crunch_weeks == (11,)
    # the player's own bye (Week 9) is upcoming
    assert stud.own_bye.bye_week == 9 and stud.own_bye.is_upcoming is True
    # +40 over replacement clears the big-upgrade bar
    assert stud.priority_verdict.verdict == "worth-it"


def test_current_waiver_priority_is_surfaced():
    wire = waiver_wire(_hand_built_state())
    assert wire.waiver_priority.current_priority == 3
    assert wire.waiver_priority.drops_to_on_claim == 12
    assert wire.waiver_priority.is_last is False


def test_post_cutdown_window_is_flagged_for_its_dates():
    # snapshot the day after the 2026 cutdown (last Tuesday of August = Aug 25)
    on_cutdown = replace(_hand_built_state(), as_of_date=date(2026, 8, 26))
    wire = waiver_wire(on_cutdown)
    assert wire.window.opens == date(2026, 8, 25)
    assert wire.window.is_open is True


def test_layer_is_pure_same_state_same_answer():
    assert waiver_wire(_hand_built_state()) == waiver_wire(_hand_built_state())
