from __future__ import annotations

from dataclasses import dataclass

# The RIP TIDE scoring ruleset, transcribed field-for-field from the league
# settings in ``PRD.md`` / spec issue #1 ("Scoring engine"). Every value here is
# meant to be diffable against that prose by a reviewer, so the rules are plain
# named floats rather than an opaque coefficient table.
#
# Scope of this module (ticket #4): offense, kicker, and team defense/special
# teams. The individual-defender ("D") slot is a separate scoring surface and
# lands in its own ticket; it is deliberately absent here.
#
# Fractional points and negative points are both ON for this league: the engine
# never rounds a component to an integer and never floors a total at zero.


@dataclass(frozen=True)
class IndividualDefenseRules:
    """Individual defensive plays, scored for whoever records them.

    RIP TIDE credits these to *any* player — a WR who makes a tackle after his
    QB is intercepted gets the solo-tackle point. The full individual-defender
    ("D" slot) surface, with its own tolerance and outlier catalogue, is a
    separate ticket; this covers only the stats that show up on offensive and
    kicking box scores.
    """

    solo_tackle: float
    assisted_tackle: float
    pass_defended: float


@dataclass(frozen=True)
class OffenseRules:
    """Offense scoring for QB / RB / WR / TE.

    Yardage is scored as ``yards / yards_per_point`` with no rounding — RIP TIDE
    runs fractional points, so 74 passing yards is exactly ``74 / 25`` points.
    """

    passing_yards_per_point: float
    rushing_yards_per_point: float
    receiving_yards_per_point: float
    # Kick/punt return yardage, scored for any position that accrues it (a WR on
    # returns, etc.). Yahoo's 2025 box scores show this at 1 point per 25 yards,
    # the same rate as passing yards.
    return_yards_per_point: float
    passing_touchdown: float
    rushing_touchdown: float
    receiving_touchdown: float
    interception_thrown: float
    sack_taken: float
    two_point_conversion: float
    individual_defense: IndividualDefenseRules
    # The PRD scoring list does not enumerate an offensive fumble-lost penalty.
    # It is kept as an explicit knob (default 0.0) so that if the 2025 golden
    # gate turns up a systematic offset explained by fumbles, the fix is a
    # one-line ruleset change rather than an engine change. See
    # docs/scoring-oracle-capture.md.
    fumble_lost: float


@dataclass(frozen=True)
class KickerRules:
    """Kicker scoring: field goals by distance band, PATs, and the short miss.

    RIP TIDE's distance tiers are 3 / 3 / 3 / 4 / 5 for 0-19, 20-29, 30-39,
    40-49, 50+. Only misses from 0-19 are penalised; longer misses are 0.
    """

    fg_made_0_19: float
    fg_made_20_29: float
    fg_made_30_39: float
    fg_made_40_49: float
    fg_made_50_plus: float
    fg_missed_0_19: float
    pat_made: float
    pat_missed: float
    individual_defense: IndividualDefenseRules


@dataclass(frozen=True)
class PointsAllowedTier:
    """One band of the team-defense points-allowed schedule.

    ``upper_bound`` is the inclusive maximum points allowed for the tier;
    ``None`` marks the final open-ended band (35 or more).
    """

    upper_bound: int | None
    points: float


@dataclass(frozen=True)
class TeamDefenseRules:
    """Team defense / special teams scoring.

    Event points are linear in the event counts; the points-allowed bonus is a
    single lookup into ``points_allowed_tiers`` (ordered low to high, ending in
    the open-ended band).
    """

    sack: float
    interception: float
    fumble_recovery: float
    touchdown: float
    safety: float
    blocked_kick: float
    tackle_for_loss: float
    # Return yardage the defense/special teams unit accrues, at 1 point per 25
    # yards (Yahoo 2025 box scores).
    return_yards_per_point: float
    points_allowed_tiers: tuple[PointsAllowedTier, ...]

    def points_allowed_bonus(self, points_allowed: float) -> float:
        """The tier bonus for surrendering ``points_allowed`` points."""
        for tier in self.points_allowed_tiers:
            if tier.upper_bound is None or points_allowed <= tier.upper_bound:
                return tier.points
        # Unreachable when the schedule ends in an open-ended band, which the
        # RIP TIDE ruleset and the validator both guarantee.
        return self.points_allowed_tiers[-1].points


@dataclass(frozen=True)
class LeagueRuleset:
    """The full scoring ruleset handed to the engine as its second argument."""

    name: str
    offense: OffenseRules
    kicker: KickerRules
    team_defense: TeamDefenseRules


_RIP_TIDE_IDP = IndividualDefenseRules(
    solo_tackle=1.0,
    assisted_tackle=0.5,
    pass_defended=1.0,
)

RIP_TIDE_RULESET = LeagueRuleset(
    name="RIP TIDE",
    offense=OffenseRules(
        passing_yards_per_point=25.0,
        rushing_yards_per_point=10.0,
        receiving_yards_per_point=10.0,
        return_yards_per_point=25.0,
        passing_touchdown=6.0,
        rushing_touchdown=6.0,
        receiving_touchdown=6.0,
        interception_thrown=-1.0,
        sack_taken=-1.0,
        two_point_conversion=2.0,
        individual_defense=_RIP_TIDE_IDP,
        fumble_lost=0.0,
    ),
    kicker=KickerRules(
        fg_made_0_19=3.0,
        fg_made_20_29=3.0,
        fg_made_30_39=3.0,
        fg_made_40_49=4.0,
        fg_made_50_plus=5.0,
        fg_missed_0_19=-1.0,
        pat_made=1.0,
        pat_missed=-1.0,
        individual_defense=_RIP_TIDE_IDP,
    ),
    team_defense=TeamDefenseRules(
        sack=2.0,
        interception=2.0,
        fumble_recovery=1.0,
        touchdown=6.0,
        safety=2.0,
        blocked_kick=2.0,
        tackle_for_loss=1.0,
        return_yards_per_point=25.0,
        points_allowed_tiers=(
            PointsAllowedTier(upper_bound=0, points=10.0),
            PointsAllowedTier(upper_bound=6, points=7.0),
            PointsAllowedTier(upper_bound=13, points=4.0),
            PointsAllowedTier(upper_bound=20, points=1.0),
            PointsAllowedTier(upper_bound=27, points=0.0),
            PointsAllowedTier(upper_bound=34, points=-1.0),
            PointsAllowedTier(upper_bound=None, points=-4.0),
        ),
    ),
)
