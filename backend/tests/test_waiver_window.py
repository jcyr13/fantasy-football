from __future__ import annotations

from datetime import date

from deadparrots.waiver import WaiverParams, roster_cutdown_window
from waiver_fixtures import a_state

# The post-roster-cutdown / practice-squad-churn waiver window (the ticket):
# flag the ~24–48h after the last-Tuesday-of-August cutdown.


def test_window_opens_on_the_cutdown_day():
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 8, 25)))
    assert flag.opens == date(2026, 8, 25)
    assert flag.closes == date(2026, 8, 27)
    assert flag.is_open is True
    assert "churning" in flag.note


def test_open_through_the_close_date():
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 8, 27)))
    assert flag.is_open is True


def test_upcoming_within_the_lookahead():
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 8, 20)))
    assert flag.is_open is False
    assert flag.is_upcoming is True
    assert flag.days_until_open == 5
    assert "day(s) out" in flag.note


def test_well_before_the_window_is_neither_open_nor_upcoming():
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 8, 1)))
    assert (flag.is_open, flag.is_upcoming) == (False, False)
    assert flag.days_until_open == 24


def test_after_the_window_has_passed():
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 10, 20)))
    assert flag.is_open is False
    assert flag.days_until_open < 0
    assert "has passed" in flag.note


def test_explicit_cutdown_date_and_window_length_are_honoured():
    params = WaiverParams(roster_cutdown_date=date(2026, 8, 26), cutdown_window_days=3)
    flag = roster_cutdown_window(a_state(as_of_date=date(2026, 8, 28)), params)
    assert flag.opens == date(2026, 8, 26)
    assert flag.closes == date(2026, 8, 29)
    assert flag.is_open is True
