from __future__ import annotations

import dataclasses
import math

import pytest

from deadparrots.simulation import CorrelationSpec, loadings_for, role_of
from deadparrots.simulation.correlation import DEFAULT_CORRELATION

# The factor-model loadings (ADR-0007). These pin the structure methodology
# §3.9 / issue #10 require: a QB and his pass-catchers move together, game
# script splits passing from rushing/defence, and every latent draw stays
# standard normal so the marginal shape is untouched.


@pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE", "K", "DEF", "IDP", "CB"])
def test_loadings_are_a_unit_variance_decomposition(position):
    c = loadings_for(position)
    assert c.team_coef**2 + c.game_coef**2 + c.idio_coef**2 == pytest.approx(1.0)


def test_qb_and_pass_catchers_share_the_team_factor_with_the_same_sign():
    qb = loadings_for("QB")
    wr = loadings_for("WR")
    te = loadings_for("TE")
    assert qb.team_coef > 0.0
    assert qb.team_coef == wr.team_coef == te.team_coef
    # induced stack correlation from the team factor alone
    assert qb.team_coef * wr.team_coef == pytest.approx(DEFAULT_CORRELATION.qb_stack_share)


def test_only_qb_and_pass_catchers_carry_a_team_stack_loading():
    # issue #10 names exactly two channels: QB-to-pass-catcher and game script.
    # Everyone else rides the shared game factor only.
    assert loadings_for("RB").team_coef == 0.0
    assert loadings_for("K").team_coef == 0.0
    assert loadings_for("DEF").team_coef == 0.0
    assert loadings_for("IDP").team_coef == 0.0


def test_game_script_sign_splits_passing_from_rushing_and_defense():
    # passing game + kicker load one way, rushing game / DEF / IDP the other
    assert loadings_for("QB").game_coef > 0.0
    assert loadings_for("WR").game_coef > 0.0
    assert loadings_for("K").game_coef > 0.0
    assert loadings_for("RB").game_coef < 0.0
    assert loadings_for("DEF").game_coef < 0.0
    assert loadings_for("IDP").game_coef < 0.0
    # same magnitude, opposite sign
    assert abs(loadings_for("WR").game_coef) == pytest.approx(abs(loadings_for("RB").game_coef))
    assert abs(loadings_for("WR").game_coef) == pytest.approx(
        math.sqrt(DEFAULT_CORRELATION.game_script_share)
    )


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("PK", "K"), ("DST", "DEF"), ("D/ST", "DEF"), ("FB", "RB"), ("cb", "IDP"),
     ("edge", "IDP"), ("wr", "WR")],
)
def test_role_aliases_resolve(alias, canonical):
    assert role_of(alias) == canonical


def test_unknown_position_gets_a_safe_weakly_correlated_default():
    # no team loading, positive game sign, still a unit decomposition — no raise
    c = loadings_for("LONG_SNAPPER")
    assert c.team_coef == 0.0
    assert c.game_coef > 0.0
    assert c.team_coef**2 + c.game_coef**2 + c.idio_coef**2 == pytest.approx(1.0)


def test_spec_rejects_shares_outside_the_unit_interval():
    with pytest.raises(ValueError):
        CorrelationSpec(qb_stack_share=-0.1)
    with pytest.raises(ValueError):
        CorrelationSpec(game_script_share=1.0)


def test_spec_rejects_a_combination_that_would_exhaust_idiosyncratic_variance():
    with pytest.raises(ValueError):
        CorrelationSpec(qb_stack_share=0.9, game_script_share=0.2)


def test_spec_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_CORRELATION.qb_stack_share = 0.5  # type: ignore[misc]
