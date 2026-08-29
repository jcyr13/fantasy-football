from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal

from .rows import PlayerWeekKey, ScoredPlayerWeek, ScoringUnit, StatRow
from .ruleset import IndividualDefenseRules, LeagueRuleset

# The scoring engine: one pure function, ``score_player_weeks``, mapping
# ``(stat rows, ruleset) -> {player-week: scored player-week}``. No network, no
# disk, no clock, no globals. Everything downstream in the app assumes this is
# correct, which is why it is validated against real 2025 Yahoo actuals before
# anything is built on it (spec issue #1, "Validation gate (hard)").


def round_points(value: float) -> float:
    """Round to two decimals, half-up, the way Yahoo reports fantasy points."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _idp_points(row: StatRow, idp: IndividualDefenseRules) -> dict[str, float]:
    """Individual-defense points RIP TIDE awards to any player who records them."""
    return {
        "tackle_solo": row.stat("tackle_solo") * idp.solo_tackle,
        "tackle_assist": row.stat("tackle_assist") * idp.assisted_tackle,
        "passes_defended": row.stat("passes_defended") * idp.pass_defended,
    }


def _score_offense(row: StatRow, ruleset: LeagueRuleset) -> dict[str, float]:
    r = ruleset.offense
    return {
        "passing_yards": row.stat("passing_yards") / r.passing_yards_per_point,
        "rushing_yards": row.stat("rushing_yards") / r.rushing_yards_per_point,
        "receiving_yards": row.stat("receiving_yards") / r.receiving_yards_per_point,
        "return_yards": row.stat("return_yards") / r.return_yards_per_point,
        "passing_touchdowns": row.stat("passing_touchdowns") * r.passing_touchdown,
        "rushing_touchdowns": row.stat("rushing_touchdowns") * r.rushing_touchdown,
        "receiving_touchdowns": row.stat("receiving_touchdowns") * r.receiving_touchdown,
        "interceptions_thrown": row.stat("interceptions_thrown") * r.interception_thrown,
        "sacks_taken": row.stat("sacks_taken") * r.sack_taken,
        "two_point_conversions": row.stat("two_point_conversions") * r.two_point_conversion,
        "fumbles_lost": row.stat("fumbles_lost") * r.fumble_lost,
        **_idp_points(row, r.individual_defense),
    }


def _score_kicker(row: StatRow, ruleset: LeagueRuleset) -> dict[str, float]:
    r = ruleset.kicker
    return {
        "fg_made_0_19": row.stat("fg_made_0_19") * r.fg_made_0_19,
        "fg_made_20_29": row.stat("fg_made_20_29") * r.fg_made_20_29,
        "fg_made_30_39": row.stat("fg_made_30_39") * r.fg_made_30_39,
        "fg_made_40_49": row.stat("fg_made_40_49") * r.fg_made_40_49,
        "fg_made_50_plus": row.stat("fg_made_50_plus") * r.fg_made_50_plus,
        "fg_missed_0_19": row.stat("fg_missed_0_19") * r.fg_missed_0_19,
        "pat_made": row.stat("pat_made") * r.pat_made,
        "pat_missed": row.stat("pat_missed") * r.pat_missed,
        **_idp_points(row, r.individual_defense),
    }


def _score_individual_defense(row: StatRow, ruleset: LeagueRuleset) -> dict[str, float]:
    """The "D" slot: one defender scored on the full individual-defense schedule.

    A distinct surface from team DEF (``_score_team_defense``) — no points-
    allowed bonus, and it scores ``forced_fumbles`` and the defender's own
    turnover-return yardage, which the team unit does not.
    """
    r = ruleset.individual_defense
    return {
        **_idp_points(row, r),  # the tackle / pass-defended lines shared with offense
        "sacks": row.stat("sacks") * r.sack,
        "interceptions": row.stat("interceptions") * r.interception,
        "forced_fumbles": row.stat("forced_fumbles") * r.forced_fumble,
        "fumble_recoveries": row.stat("fumble_recoveries") * r.fumble_recovery,
        "defensive_touchdowns": row.stat("defensive_touchdowns") * r.touchdown,
        "safeties": row.stat("safeties") * r.safety,
        "blocked_kicks": row.stat("blocked_kicks") * r.blocked_kick,
        "tackles_for_loss": row.stat("tackles_for_loss") * r.tackle_for_loss,
        "turnover_return_yards": (
            row.stat("turnover_return_yards") / r.turnover_return_yards_per_point
        ),
    }


def _score_team_defense(row: StatRow, ruleset: LeagueRuleset) -> dict[str, float]:
    r = ruleset.team_defense
    return {
        "sacks": row.stat("sacks") * r.sack,
        "interceptions": row.stat("interceptions") * r.interception,
        "fumble_recoveries": row.stat("fumble_recoveries") * r.fumble_recovery,
        "defensive_touchdowns": row.stat("defensive_touchdowns") * r.touchdown,
        "safeties": row.stat("safeties") * r.safety,
        "blocked_kicks": row.stat("blocked_kicks") * r.blocked_kick,
        "tackles_for_loss": row.stat("tackles_for_loss") * r.tackle_for_loss,
        "return_yards": row.stat("return_yards") / r.return_yards_per_point,
        "points_allowed": r.points_allowed_bonus(row.stat("points_allowed")),
    }


_SCORERS = {
    ScoringUnit.OFFENSE: _score_offense,
    ScoringUnit.KICKER: _score_kicker,
    ScoringUnit.TEAM_DEFENSE: _score_team_defense,
    ScoringUnit.INDIVIDUAL_DEFENSE: _score_individual_defense,
}


def score_row(row: StatRow, ruleset: LeagueRuleset) -> ScoredPlayerWeek:
    """Score a single row. The breakdown holds exact per-component points; the
    total is rounded half-up to two decimals.
    """
    breakdown = _SCORERS[row.unit](row, ruleset)
    total = round_points(sum(breakdown.values()))
    return ScoredPlayerWeek(
        entity_id=row.entity_id,
        season=row.season,
        week=row.week,
        unit=row.unit,
        points=total,
        breakdown=breakdown,
    )


def score_player_weeks(
    rows: Iterable[StatRow], ruleset: LeagueRuleset
) -> dict[PlayerWeekKey, ScoredPlayerWeek]:
    """Score every row, keyed by ``(entity_id, season, week)``.

    Two rows sharing a key (e.g. an offense line and a kicker line for the same
    player-week, which RIP TIDE never actually rosters together) would collide;
    the caller is responsible for not mixing units for one entity-week.
    """
    scored: dict[PlayerWeekKey, ScoredPlayerWeek] = {}
    for row in rows:
        result = score_row(row, ruleset)
        scored[result.key] = result
    return scored


def total_points(scored: Mapping[PlayerWeekKey, ScoredPlayerWeek]) -> float:
    """Sum of every scored row's points — a convenience for lineup totals."""
    return round_points(sum(week.points for week in scored.values()))
