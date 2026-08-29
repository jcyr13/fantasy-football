from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

# The correlation model for the head-to-head simulation (issue #10: "players are
# not treated as independent"; methodology §3.9 leaves the *joint* to the sim).
#
# It is a linear factor model, not a full correlation matrix. Each player's
# latent standard-normal draw is
#
#   Z_i = team_coef_i * T_{team(i)} + game_coef_i * G_{game(i)} + idio_coef_i * E_i
#
# where T, G and E are independent standard-normal factor streams keyed by NFL
# team, NFL game, and player id respectively. The coefficients are set so
# ``Var(Z_i) = 1`` exactly, so the marginal shape :mod:`marginals` describes is
# untouched. Two consequences matter:
#
#   * QB-to-pass-catcher stacks: a QB and his own WR/TE/RB all load (same sign)
#     on their NFL team's offensive factor T, so they rise and fall together.
#   * Game script: everyone in one NFL game loads on that game's factor G, with
#     a sign by role — passing games and kickers up together in a shootout,
#     rushing games / team DEF / IDP down. Opposing pass-catchers end up
#     positively correlated; a rushing attack and the other side's passing game
#     negatively.
#
# Because a player's coefficients depend only on its position and its stable
# team/game ids — never on which other players share the lineup — two candidate
# lineups that both start a player draw byte-identical points for that player.
# That is what makes the common-random-numbers guarantee (acceptance criterion
# 3) hold across candidate lineups. See ADR-0007.


@dataclass(frozen=True)
class CorrelationSpec:
    """Variance shares for the two shared factors (the rest is idiosyncratic).

    Each value is the share of a player's unit marginal variance carried by that
    factor, so a coefficient is its square root and the induced correlation
    between two players sharing a factor (same sign) is roughly the share
    itself. Defaults are placeholder magnitudes calibrated to typical
    fantasy-points correlations — a QB/WR1 stack lands near ``qb_stack_share +
    game_script_share`` — and are pinned by behaviour, not exact value
    (ADR-0007), the same way the positional residual priors are (ADR-0006).
    """

    qb_stack_share: float = 0.35
    rb_own_team_share: float = 0.12
    game_script_share: float = 0.15

    def __post_init__(self) -> None:
        for name in ("qb_stack_share", "rb_own_team_share", "game_script_share"):
            value = getattr(self, name)
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{name} must be in [0, 1): {value!r}")
        # The idiosyncratic remainder must stay strictly positive for every role
        # the model assigns a team loading to.
        for team_share in (self.qb_stack_share, self.rb_own_team_share):
            if team_share + self.game_script_share >= 1.0:
                raise ValueError(
                    "team share + game_script_share must stay below 1 "
                    f"(got {team_share} + {self.game_script_share})"
                )


DEFAULT_CORRELATION = CorrelationSpec()
"""The placeholder correlation structure the sim uses unless overridden."""


# Coarse role buckets for the loadings. Keys are canonical; aliases below map
# the nflverse / Yahoo position strings onto them.
_ROLE_ALIASES: Mapping[str, str] = {
    "PK": "K",
    "DST": "DEF",
    "D/ST": "DEF",
    "D-ST": "DEF",
    "DEFENSE": "DEF",
    "D": "IDP",
    "DB": "IDP", "CB": "IDP", "S": "IDP", "SS": "IDP", "FS": "IDP",
    "LB": "IDP", "OLB": "IDP", "ILB": "IDP", "MLB": "IDP", "EDGE": "IDP",
    "DL": "IDP", "DE": "IDP", "DT": "IDP", "NT": "IDP",
    "FB": "RB", "HB": "RB",
    "PASS_CATCHER": "WR",
}

# Sign of a role's loading on the shared NFL-game factor. Passing offence and
# the kicker move together when a game turns into a shootout; the rushing
# attack, the team defence and individual defenders move the other way.
_GAME_SCRIPT_SIGN: Mapping[str, float] = {
    "QB": 1.0,
    "WR": 1.0,
    "TE": 1.0,
    "K": 1.0,
    "RB": -1.0,
    "DEF": -1.0,
    "IDP": -1.0,
}


@dataclass(frozen=True)
class LatentLoadings:
    """The three coefficients on ``(T_team, G_game, E_player)`` for one player.

    ``team_coef**2 + game_coef**2 + idio_coef**2 == 1`` by construction, so the
    latent draw is standard normal and the marginal shape is preserved.
    """

    team_coef: float
    game_coef: float
    idio_coef: float


def role_of(position: str) -> str:
    """Canonical role bucket for a position string (``QB``/``RB``/``WR``/``TE``/
    ``K``/``DEF``/``IDP``), resolving common nflverse and Yahoo aliases.

    An unrecognised position is returned upper-cased and unchanged; it gets no
    team loading and a positive game-script sign — a safe, weakly-correlated
    default rather than a hard failure mid-simulation.
    """
    key = position.strip().upper()
    return _ROLE_ALIASES.get(key, key)


def loadings_for(
    position: str, spec: CorrelationSpec = DEFAULT_CORRELATION
) -> LatentLoadings:
    """Factor coefficients for a player at ``position`` under ``spec``."""
    role = role_of(position)

    if role in ("QB", "WR", "TE"):
        team_share = spec.qb_stack_share
    elif role == "RB":
        team_share = spec.rb_own_team_share
    else:
        team_share = 0.0

    game_share = spec.game_script_share
    idio_share = 1.0 - team_share - game_share
    # role_of guarantees the QB/WR/TE/RB branches above; any role without a team
    # loading keeps the full remainder, so idio_share is always > 0 here.

    sign = _GAME_SCRIPT_SIGN.get(role, 1.0)
    return LatentLoadings(
        team_coef=math.sqrt(team_share),
        game_coef=math.copysign(math.sqrt(game_share), sign),
        idio_coef=math.sqrt(max(idio_share, 0.0)),
    )
