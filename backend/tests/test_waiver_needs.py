from __future__ import annotations

from deadparrots.waiver import bench_need_fit, bench_need_fits
from waiver_fixtures import a_state, full_roster

# Bench-need fit (methodology §4.10–§4.11): per-role read of roster depth plus
# the per-role bye-crunch weeks, from the same §4.4 logic the Team Outlook
# layer's bye-crunch map uses.


def test_deep_role_has_no_pressing_need():
    state = a_state(roster=full_roster(wr=5))  # 5 WR behind 2 fixed slots
    fit = bench_need_fit(state, "WR")

    assert fit.depth == "deep"
    assert fit.has_current_hole is False
    assert fit.bye_crunch_weeks == ()
    assert "No pressing need at WR" in fit.summary


def test_thin_role_just_covers_its_slots():
    state = a_state(roster=full_roster(te=1))  # 1 TE, 1 fixed slot
    fit = bench_need_fit(state, "TE")

    assert fit.depth == "thin"
    assert fit.rostered_depth == 1 and fit.fixed_slots == 1
    assert "thin" in fit.summary


def test_current_bye_leaves_a_hole():
    # lone kicker on bye this week -> K is a hole
    state = a_state(roster=full_roster(k=1, byes={"k1": 8}), current_week=8)
    fit = bench_need_fit(state, "K")

    assert fit.has_current_hole is True
    assert fit.depth == "hole"
    assert fit.healthy_this_week == 0
    assert "Fills a Week 8 hole at K" in fit.summary


def test_season_ending_injury_also_leaves_a_hole():
    state = a_state(roster=full_roster(def_=1, unavailable={"def1"}))
    fit = bench_need_fit(state, "DEF")
    assert fit.has_current_hole is True
    assert fit.healthy_this_week == 0


def test_bye_crunch_weeks_flag_future_thinning():
    # two of three RB starters share a Week 11 bye
    roster = full_roster(rb=4, byes={"rb1": 11, "rb2": 11})
    state = a_state(roster=roster, current_week=8, regular_season_weeks=14)
    fit = bench_need_fit(state, "RB")

    assert fit.bye_crunch_weeks == (11,)
    assert fit.has_current_hole is False
    assert "Week 11" in fit.summary


def test_bench_players_on_bye_do_not_trigger_a_crunch_week():
    roster = full_roster(rb=5, byes={"rb1": 11, "rb4": 11, "rb5": 11}, bench={"rb4", "rb5"})
    fit = bench_need_fit(a_state(roster=roster), "RB")
    assert fit.bye_crunch_weeks == ()


def test_bench_need_fits_covers_every_fixed_slot_role():
    fits = bench_need_fits(a_state())
    assert set(fits) == {"QB", "RB", "WR", "TE", "K", "DEF", "IDP"}
