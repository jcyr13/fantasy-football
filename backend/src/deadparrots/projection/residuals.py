from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .decay import weighted_skew, weighted_std

# The *shape* half of the hybrid projection (methodology §3.2 step 2): the
# distribution of (actual - expected) fantasy points for a position, held as a
# standardised descriptor and centred on the player's own mean at sampling
# time.
#
# NOTE ON PROVENANCE: §3.2 says these come from "all players at that position
# over a large historical sample". That fit is not wired up in this ticket — the
# table below is a deliberate placeholder calibrated to §3.2's *qualitative*
# statement (WR/TE weekly outcomes are the widest and most right-skewed;
# RB less so; QB and K tightest; DEF/IDP different again). The numbers are
# exposed as an overridable argument to :func:`project` and pinned only by their
# ordering in ``test_projection_residuals.py``, so replacing them with fitted
# values is a one-line change with no interface churn.


@dataclass(frozen=True)
class ResidualPrior:
    """Standardised weekly-residual shape for a position.

    ``cv`` — residual standard deviation as a fraction of the player's projected
    volume (so the spread scales with the projection, §3.2). ``skew`` — the
    Fisher skewness fed to the sampler's Cornish-Fisher term; positive is
    right-skewed (boom weeks longer than bust weeks). Centred on 0 by
    construction.
    """

    cv: float
    skew: float

    def blend(self, other: ResidualPrior, own_weight: float) -> ResidualPrior:
        """Linear blend ``own_weight * self + (1 - own_weight) * other`` (§3.6).

        ``self`` is the player's own shape, ``other`` the positional prior;
        ``own_weight`` is ``games_this_season / own_shape_min_games`` clamped to
        ``[0, 1]``.
        """
        w = min(max(own_weight, 0.0), 1.0)
        return ResidualPrior(
            cv=w * self.cv + (1.0 - w) * other.cv,
            skew=w * self.skew + (1.0 - w) * other.skew,
        )


# Position key -> prior. Keys are the canonical RIP TIDE position groups; the
# model normalises common aliases (see ``prior_for_position``).
POSITIONAL_RESIDUAL_PRIORS: Mapping[str, ResidualPrior] = {
    "QB": ResidualPrior(cv=0.33, skew=0.15),
    "RB": ResidualPrior(cv=0.42, skew=0.35),
    "WR": ResidualPrior(cv=0.52, skew=0.55),
    "TE": ResidualPrior(cv=0.58, skew=0.60),
    "K": ResidualPrior(cv=0.40, skew=0.05),
    "DEF": ResidualPrior(cv=0.65, skew=0.40),
    "IDP": ResidualPrior(cv=0.45, skew=0.25),
}

_POSITION_ALIASES: Mapping[str, str] = {
    "PK": "K",
    "DST": "DEF",
    "D/ST": "DEF",
    "D-ST": "DEF",
    "D": "IDP",
    "DB": "IDP", "CB": "IDP", "S": "IDP", "SS": "IDP", "FS": "IDP",
    "LB": "IDP", "OLB": "IDP", "ILB": "IDP", "MLB": "IDP", "EDGE": "IDP",
    "DL": "IDP", "DE": "IDP", "DT": "IDP", "NT": "IDP",
    "FB": "RB", "HB": "RB",
}


class UnknownPositionError(ValueError):
    """A history carried a position with no residual prior and no alias.

    The model fails loudly rather than guessing a shape — positions come from
    controlled nflverse roster data, so an unmapped one is a bug upstream, not
    an exotic-but-valid input (cf. the consensus feed's "fails loudly" guard,
    ADR-0005).
    """


def prior_for_position(
    position: str,
    priors: Mapping[str, ResidualPrior] = POSITIONAL_RESIDUAL_PRIORS,
) -> ResidualPrior:
    """The positional residual prior for ``position``, resolving aliases.

    Raises :class:`UnknownPositionError` for a position that is neither a key
    of ``priors`` nor a known alias of one.
    """
    key = position.strip().upper()
    key = _POSITION_ALIASES.get(key, key)
    if key in priors:
        return priors[key]
    raise UnknownPositionError(position)


def own_residual_shape(
    residuals: Sequence[float],
    weights: Sequence[float],
    volume: float,
    *,
    volume_floor: float,
    skew_clamp: float,
) -> ResidualPrior:
    """Standardised shape of a player's *own* decay-weighted residual series.

    ``volume`` scales the standard deviation into a coefficient of variation
    (kept at or above ``volume_floor``). ``skew`` is the weighted Fisher
    skewness, clamped to ``±skew_clamp`` so a tiny sample cannot hand the
    sampler a non-monotonic mapping.
    """
    sd = weighted_std(residuals, weights)
    cv = sd / max(abs(volume), volume_floor)
    skew = weighted_skew(residuals, weights)
    skew = min(max(skew, -skew_clamp), skew_clamp)
    return ResidualPrior(cv=cv, skew=skew)
