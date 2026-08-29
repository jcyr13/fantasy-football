from __future__ import annotations

from datetime import date

from deadparrots.trade import trade_deadline_countdown
from trade_fixtures import a_state

# issue #13 — "a countdown to November 28".


def test_counts_days_to_november_28_of_the_state_season():
    cd = trade_deadline_countdown(a_state(season=2026, as_of_date=date(2026, 10, 27)))
    assert cd.target_date == date(2026, 11, 28)
    assert cd.days_remaining == 32
    assert cd.is_past is False


def test_zero_on_the_deadline_day():
    cd = trade_deadline_countdown(a_state(season=2026, as_of_date=date(2026, 11, 28)))
    assert cd.days_remaining == 0
    assert cd.is_past is False


def test_negative_and_past_after_the_deadline():
    cd = trade_deadline_countdown(a_state(season=2026, as_of_date=date(2026, 12, 5)))
    assert cd.days_remaining == -7
    assert cd.is_past is True


def test_deadline_year_follows_the_season():
    cd = trade_deadline_countdown(a_state(season=2027, as_of_date=date(2027, 1, 1)))
    assert cd.target_date == date(2027, 11, 28)
    assert cd.days_remaining == 331
