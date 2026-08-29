from __future__ import annotations

from dataclasses import dataclass

from ..projection import DEFAULT_PARAMS, PlayerProjection

# The simulation's per-player input vocabulary. Issue #10's signature is
#
#   (lineup_a_distributions, lineup_b_distributions, correlation_spec, rng_seed)
#     -> P(win), summary stats
#
# and a "distribution" here is a :class:`SimPlayer`: the three numbers that fix
# a player's marginal weekly-points shape (mean / sigma / skew — the same shape
# the projection model samples, ADR-0006) plus the identifiers the correlation
# model needs (which NFL team's offense the player rides, which NFL game they
# are in). The simulation consumes these and nothing else — it never sees a
# ``PlayerProjection``'s confidence flags, a roster slot, or a raw pull.


@dataclass(frozen=True)
class SimPlayer:
    """One player's marginal weekly RIP TIDE point distribution for the sim.

    ``mean`` / ``sigma`` / ``skew`` describe the same Cornish-Fisher shape the
    projection model reports (``mean_final`` and a residual ``cv``/``skew``);
    :func:`sim_player_from_projection` builds them from a
    :class:`PlayerProjection`. ``nfl_team`` groups a QB with his own
    pass-catchers for the stack correlation; ``game_id`` groups both NFL teams
    in one game for the game-script correlation. Either may be ``None`` when
    unknown — the player then shares no team/game factor with anyone and is
    drawn independently of the rest of the slate (its marginal shape is
    unchanged).
    """

    player_id: str
    position: str
    mean: float
    sigma: float
    skew: float
    nfl_team: str | None = None
    game_id: str | None = None


def sim_player_from_projection(
    projection: PlayerProjection,
    *,
    nfl_team: str | None = None,
    game_id: str | None = None,
    residual_volume_floor: float = DEFAULT_PARAMS.residual_volume_floor,
) -> SimPlayer:
    """Adapt a :class:`PlayerProjection` into a :class:`SimPlayer`.

    ``sigma`` is reconstructed exactly as the projection model's sampler formed
    it — ``residual_cv * max(mean_final, residual_volume_floor)`` (see
    ``projection.model._distribution_quantiles``) — so the sim and the reported
    floor/projection/ceiling describe one and the same marginal. Pass the same
    ``residual_volume_floor`` the projection ran with if it was overridden from
    the methodology default.
    """
    comp = projection.components
    sigma = comp.residual_cv * max(comp.mean_final, residual_volume_floor)
    return SimPlayer(
        player_id=projection.player_id,
        position=projection.position,
        mean=comp.mean_final,
        sigma=sigma,
        skew=comp.residual_skew,
        nfl_team=nfl_team,
        game_id=game_id,
    )
