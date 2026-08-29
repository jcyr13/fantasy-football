from __future__ import annotations

import math
from collections.abc import Sequence

# Exponential-decay helpers for the projection model (methodology §3.3). Every
# player-level trailing statistic — the residual shape, the usage trend — is
# decay-weighted with a ~4-game half-life: the most recent game gets weight 1.0
# and a game ``g`` games back gets ``0.5 ** (g / half_life)``. These functions
# are pure and independent of the rest of the model so they can be checked on
# their own against the table in §3.3.


def per_game_decay(half_life_games: float) -> float:
    """The per-game multiplicative decay factor for a given half-life.

    ``0.5 ** (1 / half_life)`` — for the methodology's 4-game half-life this is
    ``0.5 ** 0.25 ≈ 0.8409``.
    """
    if half_life_games <= 0:
        raise ValueError("half_life_games must be positive")
    return 0.5 ** (1.0 / half_life_games)


def decay_weights(n: int, half_life_games: float) -> list[float]:
    """Weights for ``n`` observations ordered **oldest → newest**.

    The last (most recent) observation gets 1.0; the observation ``k`` games
    back gets ``per_game_decay(half_life) ** k``. An empty series yields an
    empty list.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    factor = per_game_decay(half_life_games)
    # index i is (n - 1 - i) games back from the most recent
    return [factor ** (n - 1 - i) for i in range(n)]


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted arithmetic mean. Raises if the weights sum to zero."""
    _check_lengths(values, weights)
    total_w = math.fsum(weights)
    if total_w <= 0.0:
        raise ValueError("weights must sum to a positive number")
    return math.fsum(v * w for v, w in zip(values, weights)) / total_w


def _weighted_variance(values: Sequence[float], weights: Sequence[float]) -> float:
    """Population weighted variance about the weighted mean (no reliability
    correction — the decay weights are not frequencies).
    """
    _check_lengths(values, weights)
    mean = weighted_mean(values, weights)
    total_w = math.fsum(weights)
    return math.fsum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_w


def weighted_std(values: Sequence[float], weights: Sequence[float]) -> float:
    """Square root of :func:`_weighted_variance`."""
    return math.sqrt(max(_weighted_variance(values, weights), 0.0))


def weighted_skew(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted standardised third moment (Fisher skewness).

    Returns 0.0 for a degenerate series with no spread — the caller then leans
    entirely on the positional prior's skew.
    """
    _check_lengths(values, weights)
    mean = weighted_mean(values, weights)
    total_w = math.fsum(weights)
    m2 = math.fsum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_w
    if m2 <= 1e-12:
        return 0.0
    m3 = math.fsum(w * (v - mean) ** 3 for v, w in zip(values, weights)) / total_w
    return m3 / (m2**1.5)


def weighted_slope(values: Sequence[float], weights: Sequence[float]) -> float:
    """Decay-weighted least-squares slope of ``values`` against game index.

    The x-axis is ``0, 1, …, n-1`` oldest → newest, so a positive slope means
    the signal is trending up into the most recent games. Fewer than two
    observations, or no spread on the x-axis, yields 0.0.
    """
    _check_lengths(values, weights)
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    total_w = math.fsum(weights)
    if total_w <= 0.0:
        raise ValueError("weights must sum to a positive number")
    x_bar = math.fsum(w * x for x, w in zip(xs, weights)) / total_w
    y_bar = weighted_mean(values, weights)
    sxx = math.fsum(w * (x - x_bar) ** 2 for x, w in zip(xs, weights))
    if sxx <= 1e-12:
        return 0.0
    sxy = math.fsum(
        w * (x - x_bar) * (y - y_bar) for x, y, w in zip(xs, values, weights)
    )
    return sxy / sxx


def _check_lengths(values: Sequence[float], weights: Sequence[float]) -> None:
    if len(values) != len(weights):
        raise ValueError(
            f"values and weights differ in length: {len(values)} vs {len(weights)}"
        )
