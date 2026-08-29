from __future__ import annotations

import math

import pytest

from deadparrots.projection.decay import (
    decay_weights,
    per_game_decay,
    weighted_mean,
    weighted_skew,
    weighted_slope,
    weighted_std,
)

# The decay helpers back every trailing statistic in the model. These pin them
# against the worked table in methodology §3.3.


def test_per_game_decay_is_half_at_the_half_life():
    factor = per_game_decay(4.0)
    assert factor == pytest.approx(0.8408964, rel=1e-6)
    # four games back is exactly half weight
    assert factor**4 == pytest.approx(0.5, rel=1e-12)


@pytest.mark.parametrize(
    ("games_ago", "weight"),
    [(0, 1.00), (1, 0.84), (2, 0.71), (4, 0.50), (8, 0.25)],
)
def test_decay_weight_table_from_methodology_section_3_3(games_ago, weight):
    # newest-first view: weight for a game N back
    w = per_game_decay(4.0) ** games_ago
    assert w == pytest.approx(weight, abs=0.005)


def test_decay_weights_are_oldest_to_newest_ending_at_one():
    w = decay_weights(5, 4.0)
    assert w[-1] == 1.0
    assert w[0] == pytest.approx(per_game_decay(4.0) ** 4)
    assert w == sorted(w)  # monotonically increasing toward the present


def test_decay_weights_empty_and_single():
    assert decay_weights(0, 4.0) == []
    assert decay_weights(1, 4.0) == [1.0]


def test_per_game_decay_rejects_nonpositive_half_life():
    with pytest.raises(ValueError):
        per_game_decay(0.0)


def test_weighted_mean_matches_hand_computation():
    assert weighted_mean([1.0, 3.0], [1.0, 3.0]) == pytest.approx(2.5)


def test_weighted_mean_rejects_zero_weight_sum():
    with pytest.raises(ValueError):
        weighted_mean([1.0, 2.0], [0.0, 0.0])


def test_weighted_std_of_constant_series_is_zero():
    assert weighted_std([5.0, 5.0, 5.0], [0.7, 0.84, 1.0]) == 0.0


def test_weighted_std_matches_unweighted_when_weights_equal():
    values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    weights = [1.0] * len(values)
    # population standard deviation
    mean = sum(values) / len(values)
    pop = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    assert weighted_std(values, weights) == pytest.approx(pop)


def test_weighted_skew_sign_follows_the_tail():
    right = weighted_skew([0.0, 0.0, 0.0, 10.0], [1.0, 1.0, 1.0, 1.0])
    left = weighted_skew([0.0, -10.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0])
    assert right > 0.0
    assert left < 0.0
    assert weighted_skew([3.0, 3.0], [1.0, 1.0]) == 0.0  # no spread -> 0


def test_weighted_slope_positive_when_signal_climbs_into_recent_games():
    rising = [0.40, 0.45, 0.55, 0.62]
    weights = decay_weights(4, 4.0)
    assert weighted_slope(rising, weights) > 0.0
    falling = list(reversed(rising))
    assert weighted_slope(falling, weights) < 0.0


def test_weighted_slope_zero_for_flat_or_too_short_series():
    assert weighted_slope([0.5], [1.0]) == 0.0
    assert weighted_slope([0.5, 0.5, 0.5], decay_weights(3, 4.0)) == pytest.approx(0.0)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        weighted_mean([1.0, 2.0], [1.0])
