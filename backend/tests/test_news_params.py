from __future__ import annotations

import pytest

from deadparrots.news.params import DEFAULT_NEWS_PARAMS, NewsParams


def test_defaults_match_the_spec():
    # spec issue #15: "last 48 hours", "at most every ~30 minutes"
    assert DEFAULT_NEWS_PARAMS.window_hours == 48
    assert DEFAULT_NEWS_PARAMS.min_poll_interval_minutes == 30
    assert DEFAULT_NEWS_PARAMS.future_skew_minutes == 60


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_hours": 0},
        {"window_hours": -1},
        {"min_poll_interval_minutes": -5},
        {"future_skew_minutes": -1},
    ],
)
def test_invalid_values_are_rejected(kwargs):
    with pytest.raises(ValueError):
        NewsParams(**kwargs)


def test_zero_throttle_is_allowed():
    assert NewsParams(min_poll_interval_minutes=0).min_poll_interval_minutes == 0
