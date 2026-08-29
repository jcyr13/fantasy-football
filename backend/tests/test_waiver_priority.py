from __future__ import annotations

from deadparrots.waiver import (
    DEFAULT_WAIVER_PARAMS,
    WaiverParams,
    priority_verdict,
    waiver_priority_standing,
)
from waiver_fixtures import a_state

# The waiver-priority cost (methodology §4.12): no FAAB, a successful claim
# drops Dead Parrots to last. The verdict trades the value-over-replacement
# gain against the queue slot it costs.

P = DEFAULT_WAIVER_PARAMS


def test_standing_surfaces_the_current_slot_and_the_cost():
    standing = waiver_priority_standing(a_state(waiver_priority=3, team_count=12))
    assert standing.current_priority == 3
    assert standing.is_last is False
    assert standing.drops_to_on_claim == 12
    assert "drops them to last" in standing.note


def test_standing_knows_when_already_last():
    standing = waiver_priority_standing(a_state(waiver_priority=12, team_count=12))
    assert standing.is_last is True
    assert "already hold last" in standing.note


def test_no_gain_is_hold_priority():
    v = priority_verdict(0.0, a_state(waiver_priority=4))
    assert v.verdict == "hold-priority"


def test_big_gain_is_worth_it_from_any_slot():
    v = priority_verdict(P.big_upgrade_points + 1.0, a_state(waiver_priority=1))
    assert v.verdict == "worth-it"
    assert "big-upgrade bar" in v.rationale


def test_marginal_gain_while_holding_a_protected_slot_is_hold_priority():
    v = priority_verdict(
        P.marginal_upgrade_points - 1.0, a_state(waiver_priority=P.protect_priority_rank)
    )
    assert v.verdict == "hold-priority"
    assert "protected priority" in v.rationale


def test_small_gain_when_already_last_is_worth_it():
    v = priority_verdict(1.0, a_state(waiver_priority=12, team_count=12))
    assert v.verdict == "worth-it"
    assert v.already_last is True


def test_mid_gain_or_low_slot_is_marginal():
    # gain between the two bars -> marginal regardless of slot
    v = priority_verdict(
        (P.marginal_upgrade_points + P.big_upgrade_points) / 2, a_state(waiver_priority=2)
    )
    assert v.verdict == "marginal"

    # small gain but priority already outside the protected band -> marginal
    v2 = priority_verdict(
        P.marginal_upgrade_points - 1.0, a_state(waiver_priority=P.protect_priority_rank + 1)
    )
    assert v2.verdict == "marginal"


def test_thresholds_are_tunable_via_params():
    params = WaiverParams(big_upgrade_points=5.0, marginal_upgrade_points=2.0)
    v = priority_verdict(6.0, a_state(waiver_priority=1), params)
    assert v.verdict == "worth-it"
