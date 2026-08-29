from __future__ import annotations

from collections.abc import Iterable, Mapping

from .rows import ScoringUnit, StatRow

# Offensive positions nflverse tags in ``player_stats.position``. Team defense is
# not a row in that table, so ``stat_rows_from_player_stats`` covers offense and
# kickers only; the DEF rows are assembled separately (see
# ``team_defense_stat_row`` and docs/scoring-oracle-capture.md).
_OFFENSE_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "FB", "HB"})
_KICKER_POSITIONS = frozenset({"K", "PK"})

# Pure translators from nflverse's wide stat tables into the engine's canonical
# ``StatRow`` vocabulary. These live next to the engine because the 2025
# validation gate needs them and so does the projection pipeline (ticket #8),
# but the engine itself never imports them — it only knows ``StatRow``.
#
# Column names follow ``nflreadpy.load_player_stats(summary_level="week")`` as of
# the 2025 season. If nflverse renames a column, only the maps below change.

_NUMERIC = (int, float)


def _num(record: Mapping[str, object], *names: str) -> float:
    """Sum the numeric values of ``names`` present in ``record`` (None/absent = 0)."""
    total = 0.0
    for name in names:
        value = record.get(name)
        if isinstance(value, _NUMERIC) and not isinstance(value, bool):
            total += float(value)
    return total


def _identity(record: Mapping[str, object]) -> tuple[str, int, int, str | None]:
    entity_id = str(record.get("player_id") or record.get("gsis_id") or "")
    season = int(record["season"])  # type: ignore[arg-type]
    week = int(record["week"])  # type: ignore[arg-type]
    label = record.get("player_display_name") or record.get("player_name")
    return entity_id, season, week, (str(label) if label is not None else None)


def offense_stat_row(record: Mapping[str, object]) -> StatRow:
    """A QB/RB/WR/TE weekly stat line -> an ``OFFENSE`` ``StatRow``."""
    entity_id, season, week, label = _identity(record)
    stats = {
        "passing_yards": _num(record, "passing_yards"),
        "passing_touchdowns": _num(record, "passing_tds"),
        "interceptions_thrown": _num(record, "passing_interceptions", "interceptions"),
        "sacks_taken": _num(record, "sacks_suffered", "sacks"),
        "two_point_conversions": _num(
            record,
            "passing_2pt_conversions",
            "rushing_2pt_conversions",
            "receiving_2pt_conversions",
        ),
        "rushing_yards": _num(record, "rushing_yards"),
        "rushing_touchdowns": _num(record, "rushing_tds"),
        "receiving_yards": _num(record, "receiving_yards"),
        "receiving_touchdowns": _num(record, "receiving_tds"),
        "fumbles_lost": _num(
            record,
            "sack_fumbles_lost",
            "rushing_fumbles_lost",
            "receiving_fumbles_lost",
        ),
    }
    return StatRow(
        entity_id=entity_id,
        season=season,
        week=week,
        unit=ScoringUnit.OFFENSE,
        stats=stats,
        label=label,
    )


def kicker_stat_row(record: Mapping[str, object]) -> StatRow:
    """A kicker weekly stat line -> a ``KICKER`` ``StatRow``.

    nflverse splits made field goals into 10-yard bands up to ``fg_made_60_``;
    RIP TIDE's top band is 50+, so the 50-59 and 60+ nflverse bands are folded
    together here.
    """
    entity_id, season, week, label = _identity(record)
    stats = {
        "fg_made_0_19": _num(record, "fg_made_0_19"),
        "fg_made_20_29": _num(record, "fg_made_20_29"),
        "fg_made_30_39": _num(record, "fg_made_30_39"),
        "fg_made_40_49": _num(record, "fg_made_40_49"),
        "fg_made_50_plus": _num(record, "fg_made_50_59", "fg_made_60_"),
        "fg_missed_0_19": _num(record, "fg_missed_0_19"),
        "pat_made": _num(record, "pat_made"),
        "pat_missed": _num(record, "pat_missed"),
    }
    return StatRow(
        entity_id=entity_id,
        season=season,
        week=week,
        unit=ScoringUnit.KICKER,
        stats=stats,
        label=label,
    )


def stat_rows_from_player_stats(records: Iterable[Mapping[str, object]]) -> list[StatRow]:
    """Route an nflverse ``player_stats`` weekly dump into offense / kicker rows.

    One row per input record whose ``position`` is an offensive or kicking one;
    every other record (defenders, long snappers, punters, ``None``) is skipped.
    Order is preserved. This is the offense+kicker half of the golden stat-row
    fixture; team defense is added on top by the caller.
    """
    rows: list[StatRow] = []
    for record in records:
        position = str(record.get("position") or "").upper()
        if position in _KICKER_POSITIONS:
            rows.append(kicker_stat_row(record))
        elif position in _OFFENSE_POSITIONS:
            rows.append(offense_stat_row(record))
    return rows


def team_defense_stat_row(
    *,
    team: str,
    season: int,
    week: int,
    sacks: float = 0.0,
    interceptions: float = 0.0,
    fumble_recoveries: float = 0.0,
    defensive_touchdowns: float = 0.0,
    safeties: float = 0.0,
    blocked_kicks: float = 0.0,
    tackles_for_loss: float = 0.0,
    points_allowed: float = 0.0,
    label: str | None = None,
) -> StatRow:
    """Assemble a ``TEAM_DEFENSE`` ``StatRow`` from already-aggregated team-week
    counts. Team defense is not a row in ``load_player_stats``; these numbers are
    rolled up from play-by-play / the schedule by the caller (the gate's capture
    step, and later the ingestion layer).
    """
    return StatRow(
        entity_id=team,
        season=season,
        week=week,
        unit=ScoringUnit.TEAM_DEFENSE,
        stats={
            "sacks": sacks,
            "interceptions": interceptions,
            "fumble_recoveries": fumble_recoveries,
            "defensive_touchdowns": defensive_touchdowns,
            "safeties": safeties,
            "blocked_kicks": blocked_kicks,
            "tackles_for_loss": tackles_for_loss,
            "points_allowed": points_allowed,
        },
        label=label or team,
    )
