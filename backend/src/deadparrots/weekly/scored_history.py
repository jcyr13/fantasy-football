from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..scoring import (
    RIP_TIDE_RULESET,
    LeagueRuleset,
    ScoringUnit,
    StatRow,
    score_player_weeks,
)

# nflverse ``player_stats`` rows → ``scoring.StatRow`` → the *validated* engine
# (ADR-0005: never a second scoring implementation). Produces each resolved
# player's RIP TIDE points per completed week — the ``actual_points`` the
# projection model's residual shape learns from (ADR-0013 §3).
#
# Team DEF is not scored here: its points come from a points-allowed schedule
# over game results, not the player-stats frame, so a rostered DEF falls back to
# its Yahoo projection in v1 (named in the assembled view's caveats).

__all__ = [
    "ScoredGame",
    "scored_games_by_player",
    "stat_rows_from_player_stats",
]

_OFFENSE_POSITIONS = frozenset({"QB", "RB", "FB", "HB", "WR", "TE"})
_KICKER_POSITIONS = frozenset({"K", "PK"})
_IDP_POSITIONS = frozenset(
    {
        "DB", "CB", "S", "SS", "FS", "LB", "OLB", "ILB", "MLB",
        "EDGE", "DL", "DE", "DT", "NT", "D", "IDP",
    }
)

# canonical offense key -> the nflverse columns that feed it (summed)
_OFFENSE_MAP: Mapping[str, tuple[str, ...]] = {
    "passing_yards": ("passing_yards",),
    "passing_touchdowns": ("passing_tds",),
    "interceptions_thrown": ("passing_interceptions", "interceptions"),
    "sacks_taken": ("sacks_suffered", "sacks_taken"),
    "two_point_conversions": (
        "passing_2pt_conversions",
        "rushing_2pt_conversions",
        "receiving_2pt_conversions",
    ),
    "rushing_yards": ("rushing_yards",),
    "rushing_touchdowns": ("rushing_tds",),
    "receiving_yards": ("receiving_yards",),
    "receiving_touchdowns": ("receiving_tds",),
    "fumbles_lost": (
        "rushing_fumbles_lost",
        "receiving_fumbles_lost",
        "sack_fumbles_lost",
    ),
    "return_yards": ("special_teams_return_yards",),
    "tackle_solo": ("def_tackles_solo",),
    "tackle_assist": ("def_tackle_assists", "def_tackles_with_assist"),
    "passes_defended": ("def_pass_defended", "def_passes_defended"),
}

_KICKER_MAP: Mapping[str, tuple[str, ...]] = {
    "fg_made_0_19": ("fg_made_0_19",),
    "fg_made_20_29": ("fg_made_20_29",),
    "fg_made_30_39": ("fg_made_30_39",),
    "fg_made_40_49": ("fg_made_40_49",),
    "fg_made_50_plus": ("fg_made_50_59", "fg_made_60_", "fg_made_50_plus"),
    "fg_missed_0_19": ("fg_missed_0_19",),
    "pat_made": ("pat_made",),
    "pat_missed": ("pat_missed",),
    "tackle_solo": ("def_tackles_solo",),
    "tackle_assist": ("def_tackle_assists", "def_tackles_with_assist"),
    "passes_defended": ("def_pass_defended", "def_passes_defended"),
}

_IDP_MAP: Mapping[str, tuple[str, ...]] = {
    "tackle_solo": ("def_tackles_solo",),
    "tackle_assist": ("def_tackle_assists", "def_tackles_with_assist"),
    "passes_defended": ("def_pass_defended", "def_passes_defended"),
    "sacks": ("def_sacks",),
    "interceptions": ("def_interceptions",),
    "forced_fumbles": ("def_fumbles_forced",),
    "fumble_recoveries": ("fumble_recovery_own", "fumble_recovery_opp"),
    "defensive_touchdowns": ("def_tds",),
    "safeties": ("def_safeties",),
    "tackles_for_loss": ("def_tackles_for_loss",),
    "turnover_return_yards": ("def_interception_yards", "fumble_recovery_yards"),
}


@dataclass(frozen=True)
class ScoredGame:
    """One resolved player's RIP TIDE total for one completed week."""

    week: int
    points: float


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _unit_for_position(position: str) -> ScoringUnit | None:
    pos = (position or "").strip().upper()
    if pos in _OFFENSE_POSITIONS:
        return ScoringUnit.OFFENSE
    if pos in _KICKER_POSITIONS:
        return ScoringUnit.KICKER
    if pos in _IDP_POSITIONS:
        return ScoringUnit.INDIVIDUAL_DEFENSE
    return None


def _mapped_stats(
    row: Mapping[str, object], mapping: Mapping[str, tuple[str, ...]]
) -> dict[str, float]:
    stats: dict[str, float] = {}
    for canonical, columns in mapping.items():
        total = sum(_num(row.get(col)) for col in columns)
        if total:
            stats[canonical] = total
    return stats


def stat_rows_from_player_stats(
    rows: Iterable[Mapping[str, object]],
    *,
    id_for: Mapping[str, str] | None = None,
) -> list[StatRow]:
    """One ``StatRow`` per usable player-week in an nflverse ``player_stats``
    payload.

    ``id_for`` optionally remaps the raw ``player_id`` onto the resolved id the
    rest of the weekly assembly uses; unmapped players keep their nflverse id.
    Rows for positions the RIP TIDE league never scores individually (OL, P, LS)
    are skipped.
    """
    out: list[StatRow] = []
    for row in rows:
        raw_id = str(row.get("player_id") or row.get("gsis_id") or "").strip()
        if not raw_id:
            continue
        unit = _unit_for_position(str(row.get("position") or ""))
        if unit is None:
            continue
        season = int(_num(row.get("season")))
        week = int(_num(row.get("week")))
        if week <= 0:
            continue
        mapping = {
            ScoringUnit.INDIVIDUAL_DEFENSE: _IDP_MAP,
            ScoringUnit.KICKER: _KICKER_MAP,
        }.get(unit, _OFFENSE_MAP)
        stats = _mapped_stats(row, mapping)
        entity_id = (id_for or {}).get(raw_id, raw_id)
        out.append(
            StatRow(
                entity_id=entity_id,
                season=season,
                week=week,
                unit=unit,
                stats=stats,
                label=str(row.get("player_display_name") or row.get("player_name") or ""),
            )
        )
    return out


def scored_games_by_player(
    stat_rows: Sequence[StatRow],
    *,
    ruleset: LeagueRuleset = RIP_TIDE_RULESET,
) -> dict[str, list[ScoredGame]]:
    """``player_id`` → completed-week :class:`ScoredGame` list, oldest first."""
    scored = score_player_weeks(stat_rows, ruleset)
    by_player: dict[str, list[ScoredGame]] = {}
    for (entity_id, _season, week), result in scored.items():
        by_player.setdefault(entity_id, []).append(
            ScoredGame(week=week, points=result.points)
        )
    for games in by_player.values():
        games.sort(key=lambda g: g.week)
    return by_player
