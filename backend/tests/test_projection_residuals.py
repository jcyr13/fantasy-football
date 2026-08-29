from __future__ import annotations

import pytest

from deadparrots.projection.decay import decay_weights
from deadparrots.projection.residuals import (
    POSITIONAL_RESIDUAL_PRIORS,
    ResidualPrior,
    UnknownPositionError,
    own_residual_shape,
    prior_for_position,
)

# The positional priors are placeholder magnitudes (see residuals.py) — these
# tests pin their *ordering*, which is what methodology §3.2 actually asserts:
# pass-catchers are the widest and most right-skewed, QB/K the tightest.


def test_pass_catchers_are_wider_and_more_right_skewed_than_qb():
    qb = POSITIONAL_RESIDUAL_PRIORS["QB"]
    wr = POSITIONAL_RESIDUAL_PRIORS["WR"]
    te = POSITIONAL_RESIDUAL_PRIORS["TE"]
    rb = POSITIONAL_RESIDUAL_PRIORS["RB"]
    assert wr.cv > rb.cv > qb.cv
    assert te.cv > rb.cv
    assert wr.skew > rb.skew > qb.skew
    assert min(p.skew for p in POSITIONAL_RESIDUAL_PRIORS.values()) >= 0.0


def test_every_prior_is_a_positive_finite_cv():
    for pos, prior in POSITIONAL_RESIDUAL_PRIORS.items():
        assert prior.cv > 0.0, pos
        assert prior.cv < 2.0, pos


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("PK", "K"), ("DST", "DEF"), ("D/ST", "DEF"), ("FB", "RB"), ("CB", "IDP"),
     ("edge", "IDP"), ("wr", "WR")],
)
def test_position_aliases_resolve(alias, canonical):
    assert prior_for_position(alias) == POSITIONAL_RESIDUAL_PRIORS[canonical]


def test_unknown_position_raises_rather_than_guessing_a_shape():
    with pytest.raises(UnknownPositionError):
        prior_for_position("LONG_SNAPPER")


def test_blend_endpoints_and_midpoint():
    own = ResidualPrior(cv=0.10, skew=1.0)
    prior = ResidualPrior(cv=0.50, skew=0.0)
    assert own.blend(prior, 0.0) == prior
    assert own.blend(prior, 1.0) == own
    mid = own.blend(prior, 0.5)
    assert mid.cv == pytest.approx(0.30)
    assert mid.skew == pytest.approx(0.50)


def test_blend_clamps_weight_outside_unit_interval():
    own = ResidualPrior(cv=0.10, skew=1.0)
    prior = ResidualPrior(cv=0.50, skew=0.0)
    assert own.blend(prior, 5.0) == own
    assert own.blend(prior, -1.0) == prior


def test_own_residual_shape_scales_sd_by_volume_and_clamps_skew():
    # residuals with a clear right tail
    residuals = [-1.0, -1.0, -1.0, 9.0]
    weights = decay_weights(4, 4.0)
    shape = own_residual_shape(
        residuals, weights, volume=20.0, volume_floor=3.0, skew_clamp=1.5
    )
    assert 0.0 < shape.cv < 1.0
    assert 0.0 < shape.skew <= 1.5


def test_own_residual_shape_uses_volume_floor_for_tiny_projections():
    residuals = [2.0, -2.0, 2.0, -2.0]
    weights = decay_weights(4, 4.0)
    tiny = own_residual_shape(
        residuals, weights, volume=0.1, volume_floor=3.0, skew_clamp=1.5
    )
    # sd / 3.0, not sd / 0.1
    assert tiny.cv < 1.0
