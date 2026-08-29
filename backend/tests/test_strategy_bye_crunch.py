from __future__ import annotations

from deadparrots.strategy import bye_crunch_map
from strategy_helpers import full_roster, league

# methodology §4.4 — per upcoming week, count Dead Parrots starters on bye by
# position; warn at 2 at a position, critical at 3+ or any week a legal healthy
# lineup cannot be fielded.


def _map_for(roster, *, current_week=8, regular_season_weeks=10):
    state = league(
        dp_scores=[100.0] * 7,
        current_week=current_week,
        roster=roster,
        regular_season_weeks=regular_season_weeks,
    )
    return bye_crunch_map(state)


def test_clean_week_grades_ok():
    result = _map_for(full_roster())
    assert [w.week for w in result.weeks] == [8, 9, 10]
    assert all(w.grade == "ok" for w in result.weeks)
    assert result.worst_grade == "ok"


def test_two_starters_on_bye_at_one_position_is_warn():
    roster = full_roster(byes={"wr1": 9, "wr2": 9})
    result = _map_for(roster)

    wk9 = result.week(9)
    assert wk9.grade == "warn"
    assert wk9.max_at_one_position == 2
    assert wk9.can_field_legal_lineup is True
    wr_row = next(p for p in wk9.per_position if p.role == "WR")
    assert wr_row.starters_on_bye == 2
    assert wr_row.starter_names == ("wr1", "wr2")
    # other weeks untouched
    assert result.week(8).grade == "ok"
    assert result.week(10).grade == "ok"


def test_three_starters_on_bye_at_one_position_is_critical_by_count():
    # K only needs one starter, so 3 kickers out still leaves a fieldable
    # lineup — the grade is critical purely on the count.
    roster = full_roster(k=4, byes={"k1": 9, "k2": 9, "k3": 9})
    wk9 = _map_for(roster).week(9)

    assert wk9.grade == "critical"
    assert wk9.max_at_one_position == 3
    assert wk9.can_field_legal_lineup is True


def test_week_with_no_fieldable_lineup_is_critical():
    # One QB, and he is on bye in week 9 — no legal lineup exists.
    roster = full_roster(qb=1, byes={"qb1": 9})
    wk9 = _map_for(roster).week(9)

    assert wk9.grade == "critical"
    assert wk9.can_field_legal_lineup is False
    assert any("legal healthy lineup" in r for r in wk9.reasons)


def test_bench_players_on_bye_do_not_count_toward_the_threshold():
    # wr4/wr5 are bench; only wr1 (a starter) is on bye in week 9, and wr2/wr3
    # still cover a legal lineup.
    roster = full_roster(
        wr=5, byes={"wr1": 9, "wr4": 9, "wr5": 9}, bench={"wr4", "wr5"}
    )
    wk9 = _map_for(roster).week(9)

    assert wk9.can_field_legal_lineup is True
    assert wk9.max_at_one_position == 1
    assert wk9.grade == "ok"


def test_season_ending_injury_shrinks_the_fieldable_pool():
    # Only IDP starter is hurt for the year; week with his bye can't be filled.
    roster = full_roster(idp=1, unavailable={"idp1"})
    result = _map_for(roster)
    assert all(not w.can_field_legal_lineup for w in result.weeks)
    assert all(w.grade == "critical" for w in result.weeks)
