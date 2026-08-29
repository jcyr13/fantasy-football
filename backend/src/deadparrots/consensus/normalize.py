from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..scoring import (
    RIP_TIDE_RULESET,
    ScoringUnit,
    StatRow,
    UnknownStatError,
    score_row,
)
from ..scoring.rows import STATS_BY_UNIT
from .models import ConsensusFeed, ConsensusProjection
from .raw import RawConsensusPayload

# recorded-payload-in -> normalized-objects-out (spec issue #8, acceptance
# criterion 4). ``normalize`` is pure: a recorded JSON payload in, a
# ``ConsensusFeed`` of RIP TIDE-scored projections out, no I/O. The browser /
# subprocess / HTTP step that produces the payload is a separate seam
# (``sources.py``) and is not unit-tested.
#
# Re-scoring to RIP TIDE rules (criterion 1) happens here and only here, through
# the *validated* scoring engine (``score_row`` + ``RIP_TIDE_RULESET``) — there
# is no second points implementation (docs/adr/0003). Each source hands us a
# consensus *stat line*; we translate its stat keys to the engine's canonical
# vocabulary and let the engine assign the points.

# Tokens a source renders in a numeric cell when there is no value.
_BLANK = {"", "-", "--", "---", "n/a", "na", "null", "none", "nan"}


class ConsensusNormalizationError(ValueError):
    """A recorded consensus payload is missing structure the model depends on."""

    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"{source}: {message}")


# --- position -> scoring unit ------------------------------------------------

_OFFENSE_POSITIONS = frozenset({"QB", "RB", "FB", "HB", "WR", "TE"})
_KICKER_POSITIONS = frozenset({"K", "PK"})
_TEAM_DEFENSE_POSITIONS = frozenset({"DEF", "DST", "D/ST", "D-ST", "TEAM"})
_INDIVIDUAL_DEFENSE_POSITIONS = frozenset(
    {
        "D", "IDP", "DB", "CB", "S", "SS", "FS",
        "LB", "OLB", "ILB", "MLB", "EDGE",
        "DL", "DE", "DT", "NT",
    }
)


def _unit_for_position(position: str) -> ScoringUnit | None:
    """The RIP TIDE scoring unit a consensus player belongs to, or ``None`` for a
    position the league never rosters (OL, P, LS, coaches, unknown). Those rows
    are dropped, not an error — a consensus feed carries plenty the model does
    not score, the same way unmapped stat keys are dropped.
    """
    pos = position.strip().upper()
    if pos in _OFFENSE_POSITIONS:
        return ScoringUnit.OFFENSE
    if pos in _KICKER_POSITIONS:
        return ScoringUnit.KICKER
    if pos in _TEAM_DEFENSE_POSITIONS:
        return ScoringUnit.TEAM_DEFENSE
    if pos in _INDIVIDUAL_DEFENSE_POSITIONS:
        return ScoringUnit.INDIVIDUAL_DEFENSE
    return None


# --- source stat key -> canonical engine stat key -------------------------
#
# Only keys listed here are scored; any other key in a source's stat line
# (PPR receptions, prop bonuses, kick-return props, …) is ignored on purpose —
# RIP TIDE does not score it. Keys that map to the same canonical key are
# summed (e.g. the three kinds of two-point conversion).
#
# The left-hand keys of ``_FFANALYTICS_STAT_MAP`` are the contract with
# ``rsidecar/run.R`` (its ``STAT_COLS`` right-hand values); a drift between the
# two is caught by ``test_consensus_stat_maps.py`` against the recorded fixture.

_FFANALYTICS_STAT_MAP: Mapping[str, str] = {
    # offense
    "pass_yds": "passing_yards",
    "pass_tds": "passing_touchdowns",
    "pass_int": "interceptions_thrown",
    "sacks": "sacks_taken",
    "two_pts": "two_point_conversions",
    "rush_yds": "rushing_yards",
    "rush_tds": "rushing_touchdowns",
    "rec_yds": "receiving_yards",
    "rec_tds": "receiving_touchdowns",
    "return_yds": "return_yards",
    "fumbles_lost": "fumbles_lost",
    # kicker (ffanalytics distance buckets)
    "fg_0019": "fg_made_0_19",
    "fg_2029": "fg_made_20_29",
    "fg_3039": "fg_made_30_39",
    "fg_4049": "fg_made_40_49",
    "fg_50": "fg_made_50_plus",
    "fg_miss_0019": "fg_missed_0_19",
    "xp": "pat_made",
    "xp_miss": "pat_missed",
    # team defense
    "dst_sacks": "sacks",
    "dst_int": "interceptions",
    "dst_fum_rec": "fumble_recoveries",
    "dst_td": "defensive_touchdowns",
    "dst_ret_tds": "defensive_touchdowns",
    "dst_safety": "safeties",
    "dst_blk": "blocked_kicks",
    "dst_tfl": "tackles_for_loss",
    "dst_ret_yds": "return_yards",
    "dst_pts_allowed": "points_allowed",
    # individual defender ("D" slot)
    "idp_solo": "tackle_solo",
    "idp_asst": "tackle_assist",
    "idp_pd": "passes_defended",
    "idp_sack": "sacks",
    "idp_int": "interceptions",
    "idp_fum_force": "forced_fumbles",
    "idp_fum_rec": "fumble_recoveries",
    "idp_td": "defensive_touchdowns",
    "idp_safety": "safeties",
    "idp_blk": "blocked_kicks",
    "idp_tfl": "tackles_for_loss",
    "idp_ret_yds": "turnover_return_yards",
}

_SLEEPER_STAT_MAP: Mapping[str, str] = {
    # offense
    "pass_yd": "passing_yards",
    "pass_td": "passing_touchdowns",
    "pass_int": "interceptions_thrown",
    "pass_sack": "sacks_taken",
    "pass_2pt": "two_point_conversions",
    "rush_2pt": "two_point_conversions",
    "rec_2pt": "two_point_conversions",
    "rush_yd": "rushing_yards",
    "rush_td": "rushing_touchdowns",
    "rec_yd": "receiving_yards",
    "rec_td": "receiving_touchdowns",
    "kr_yd": "return_yards",
    "pr_yd": "return_yards",
    "fum_lost": "fumbles_lost",
    # kicker
    "fgm_0_19": "fg_made_0_19",
    "fgm_20_29": "fg_made_20_29",
    "fgm_30_39": "fg_made_30_39",
    "fgm_40_49": "fg_made_40_49",
    "fgm_50p": "fg_made_50_plus",
    "fgmiss_0_19": "fg_missed_0_19",
    "xpm": "pat_made",
    "xpmiss": "pat_missed",
    # team defense
    "sack": "sacks",
    "int": "interceptions",
    "fum_rec": "fumble_recoveries",
    "def_td": "defensive_touchdowns",
    "def_st_td": "defensive_touchdowns",
    "safe": "safeties",
    "blk_kick": "blocked_kicks",
    "def_tfl": "tackles_for_loss",
    "def_kr_yd": "return_yards",
    "def_pr_yd": "return_yards",
    "pts_allow": "points_allowed",
    # individual defender ("D" slot)
    "idp_tkl_solo": "tackle_solo",
    "idp_tkl_ast": "tackle_assist",
    "idp_pass_def": "passes_defended",
    "idp_sack": "sacks",
    "idp_int": "interceptions",
    "idp_ff": "forced_fumbles",
    "idp_fum_rec": "fumble_recoveries",
    "idp_def_td": "defensive_touchdowns",
    "idp_safe": "safeties",
    "idp_blk_kick": "blocked_kicks",
    "idp_tkl_loss": "tackles_for_loss",
    "idp_int_ret_yd": "turnover_return_yards",
    "idp_fum_ret_yd": "turnover_return_yards",
}

SOURCE_STAT_MAPS: Mapping[str, Mapping[str, str]] = {
    "ffanalytics": _FFANALYTICS_STAT_MAP,
    "sleeper": _SLEEPER_STAT_MAP,
}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.casefold() in _BLANK:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _canonical_stats(
    stat_map: Mapping[str, str], allowed: frozenset[str], raw_stats: Mapping[str, Any]
) -> dict[str, float]:
    """Translate a source's stat line into the engine's canonical keys for one
    unit, summing keys that collapse together and dropping unscored ones.
    """
    out: dict[str, float] = {}
    for key, value in raw_stats.items():
        canonical = stat_map.get(key)
        if canonical is None or canonical not in allowed:
            continue
        number = _to_float(value)
        if number is None or number == 0.0:
            continue
        out[canonical] = out.get(canonical, 0.0) + number
    return out


def _require(source: str, obj: Mapping[str, Any], key: str) -> Any:
    if key not in obj or obj[key] is None:
        raise ConsensusNormalizationError(source, f"missing required field {key!r}")
    return obj[key]


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entity_id(player: Mapping[str, Any], fallback: str) -> str:
    for key in ("gsis_id", "player_id", "sleeper_id", "id"):
        value = _opt_str(player.get(key))
        if value:
            return value
    return "name:" + fallback.casefold().replace(" ", "-")


def _projection(
    source: str,
    player: Mapping[str, Any],
    *,
    season: int,
    week: int,
) -> ConsensusProjection | None:
    if not isinstance(player, Mapping):
        raise ConsensusNormalizationError(source, "a player row is not an object")

    name = str(_require(source, player, "name")).strip()
    if not name:
        raise ConsensusNormalizationError(source, "a player row has an empty name")
    position = str(_require(source, player, "position")).strip()
    unit = _unit_for_position(position)
    if unit is None:  # a position the league never rosters — drop the row
        return None
    entity_id = _entity_id(player, name)

    raw_stats = player.get("stats") or {}
    if not isinstance(raw_stats, Mapping):
        raise ConsensusNormalizationError(source, f"{name}: 'stats' is not an object")

    scored_stats = _canonical_stats(
        SOURCE_STAT_MAPS[source], STATS_BY_UNIT[unit], raw_stats
    )
    try:
        row = StatRow(entity_id, season, week, unit, scored_stats)
    except UnknownStatError as exc:  # pragma: no cover - _canonical_stats filters first
        raise ConsensusNormalizationError(source, f"{name}: {exc}") from exc

    return ConsensusProjection(
        entity_id=entity_id,
        player_name=name,
        nfl_team=_opt_str(player.get("team")),
        position=position,
        season=season,
        week=week,
        unit=unit,
        projection=score_row(row, RIP_TIDE_RULESET).points,
        scored_stats=scored_stats,
        source_points=_to_float(player.get("source_points")),
        gsis_id=_opt_str(player.get("gsis_id")),
        sleeper_id=_opt_str(player.get("sleeper_id") or player.get("player_id")),
    )


def normalize(payload: RawConsensusPayload) -> ConsensusFeed:
    """Turn a recorded consensus payload into a RIP TIDE-scored ``ConsensusFeed``.

    Validates the envelope, resolves each player's scoring unit from its
    position, translates the source's stat keys to the engine's vocabulary, and
    scores every line through ``RIP_TIDE_RULESET``. Pure — no I/O.
    """
    try:
        data = payload.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ConsensusNormalizationError(
            payload.source, f"payload is not valid JSON ({exc})"
        ) from exc
    if not isinstance(data, Mapping):
        raise ConsensusNormalizationError(payload.source, "payload is not a JSON object")

    source = str(_require(payload.source, data, "source")).strip()
    if source not in SOURCE_STAT_MAPS:
        raise ConsensusNormalizationError(
            payload.source, f"no stat-key map for source {source!r}"
        )

    season = int(_require(source, data, "season"))
    week = int(_require(source, data, "week"))
    players = _require(source, data, "players")
    if not isinstance(players, list) or not players:
        raise ConsensusNormalizationError(source, "'players' is empty or not a list")

    generated_at = _parse_dt(data.get("generated_at"))
    projections = tuple(
        p
        for p in (_projection(source, row, season=season, week=week) for row in players)
        if p is not None
    )
    if not projections:
        raise ConsensusNormalizationError(source, "no rosterable players in the feed")
    _guard_stat_map_is_live(source, projections)

    return ConsensusFeed(
        source=source,
        season=season,
        week=week,
        generated_at=generated_at,
        projections=projections,
    )


def _guard_stat_map_is_live(
    source: str, projections: tuple[ConsensusProjection, ...]
) -> None:
    """Fail loudly when a whole scoring unit produced no scorable stat — the
    signal that the source renamed a block of fields and the stat-key map is
    stale (a partial rename would otherwise pass silently as zero-point players).
    """
    scored_by_unit: dict[ScoringUnit, bool] = {}
    for p in projections:
        scored_by_unit[p.unit] = scored_by_unit.get(p.unit, False) or bool(p.scored_stats)
    dead = sorted(unit.value for unit, live in scored_by_unit.items() if not live)
    if dead:
        raise ConsensusNormalizationError(
            source,
            f"no {', '.join(dead)} player produced a scorable stat line "
            "(stat-key map is stale?)",
        )


def _parse_dt(value: Any) -> datetime:
    text = _opt_str(value)
    if text is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
