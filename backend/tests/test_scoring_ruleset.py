from __future__ import annotations

import dataclasses

import pytest

from deadparrots.scoring import RIP_TIDE_RULESET
from deadparrots.scoring.ruleset import PointsAllowedTier

# These assertions pin RIP_TIDE_RULESET field-for-field against the league
# scoring settings in PRD.md / spec issue #1. A reviewer should be able to read
# this file against that prose and see every number accounted for.


def test_offense_rules_match_the_spec():
    o = RIP_TIDE_RULESET.offense
    assert o.passing_yards_per_point == 25.0
    assert o.rushing_yards_per_point == 10.0
    assert o.receiving_yards_per_point == 10.0
    assert o.passing_touchdown == 6.0
    assert o.rushing_touchdown == 6.0
    assert o.receiving_touchdown == 6.0
    assert o.interception_thrown == -1.0
    assert o.sack_taken == -1.0
    assert o.two_point_conversion == 2.0
    # The PRD scoring list enumerates no offensive fumble-lost penalty; the knob
    # defaults to zero pending the 2025 golden gate.
    assert o.fumble_lost == 0.0


def test_kicker_rules_match_the_spec():
    k = RIP_TIDE_RULESET.kicker
    assert (k.fg_made_0_19, k.fg_made_20_29, k.fg_made_30_39) == (3.0, 3.0, 3.0)
    assert k.fg_made_40_49 == 4.0
    assert k.fg_made_50_plus == 5.0
    assert k.fg_missed_0_19 == -1.0
    assert k.pat_made == 1.0
    assert k.pat_missed == -1.0


def test_team_defense_event_rules_match_the_spec():
    d = RIP_TIDE_RULESET.team_defense
    assert d.sack == 2.0
    assert d.interception == 2.0
    assert d.fumble_recovery == 1.0
    assert d.touchdown == 6.0
    assert d.safety == 2.0
    assert d.blocked_kick == 2.0
    assert d.tackle_for_loss == 1.0


def test_points_allowed_schedule_is_10_7_4_1_0_minus1_minus4():
    tiers = RIP_TIDE_RULESET.team_defense.points_allowed_tiers
    assert [t.points for t in tiers] == [10.0, 7.0, 4.0, 1.0, 0.0, -1.0, -4.0]
    assert [t.upper_bound for t in tiers] == [0, 6, 13, 20, 27, 34, None]


@pytest.mark.parametrize(
    ("points_allowed", "bonus"),
    [
        (0, 10.0),
        (3, 7.0),
        (6, 7.0),
        (7, 4.0),
        (13, 4.0),
        (14, 1.0),
        (20, 1.0),
        (21, 0.0),
        (27, 0.0),
        (28, -1.0),
        (34, -1.0),
        (35, -4.0),
        (49, -4.0),
    ],
)
def test_points_allowed_bonus_lookup_at_every_tier_boundary(points_allowed, bonus):
    assert RIP_TIDE_RULESET.team_defense.points_allowed_bonus(points_allowed) == bonus


def test_ruleset_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RIP_TIDE_RULESET.offense.passing_touchdown = 4.0  # type: ignore[misc]


def test_custom_points_allowed_schedule_without_open_band_still_returns_a_value():
    # Defensive: a hand-built schedule that forgets the open-ended band should
    # fall back to the last tier rather than raise.
    d = dataclasses.replace(
        RIP_TIDE_RULESET.team_defense,
        points_allowed_tiers=(PointsAllowedTier(upper_bound=10, points=5.0),),
    )
    assert d.points_allowed_bonus(99) == 5.0
