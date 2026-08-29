from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .rows import STATS_BY_UNIT, ScoringUnit, StatRow

# The 2025 validation "oracle": real Yahoo per-player weekly fantasy points for
# the RIP TIDE League, captured once from Yahoo's own box scores and frozen as
# golden fixtures. The scoring engine is not trusted until its output reproduces
# these exactly for every offense / kicker / team-DEF player-week (spec issue #1),
# and to within ±1.0 for every individual-defender ("D" slot) player-week, with
# each out-of-tolerance week catalogued and explained (ticket #5).
#
# How the raw file is captured: Yahoo's Fantasy API is not reachable for this
# league (the developer account cannot attach the Fantasy Sports permission), so
# the source is a browser scrape of the archived 2025 league's per-team weekly
# box scores — each of which lists every player's stat-by-stat breakdown and
# Yahoo's own fantasy total. That raw scrape lives at ``BOX_SCORE_RAW_PATH``;
# this module transforms it into the two gate fixtures. See
# docs/scoring-oracle-capture.md.
#
# Sample scope: weeks 1, 5, 9 and 13, all 12 teams (starters + bench). Enough
# player-weeks across every position and scoring situation to pin the ruleset;
# widen the scrape and re-run ``build`` to grow it. Individual defenders (rows
# with only tackle / sack / takeaway lines) are classified and emitted too — the
# gate holds them to ±1.0, not the cent.
#
# This module is the ONLY file in ``deadparrots.scoring`` that touches disk; the
# engine never imports it.
#
# Run:  python -m deadparrots.scoring.oracle build

RIP_TIDE_LEAGUE_ID_2025 = 195010  # the archived 2025 instance (2026 is 735806)
ORACLE_SEASON = 2025

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scoring"
BOX_SCORE_RAW_PATH = _FIXTURE_DIR / "yahoo_2025_box_scores.raw.json"
ORACLE_FIXTURE_PATH = _FIXTURE_DIR / "yahoo_2025_oracle.json"
STAT_ROWS_FIXTURE_PATH = _FIXTURE_DIR / "yahoo_2025_stat_rows.json"
# Hand-maintained: every individual-defender player-week whose engine score is
# more than ``IDP_TOLERANCE`` off Yahoo, each with a stated cause. The IDP gate
# fails on any out-of-tolerance week that is not catalogued here (ticket #5).
IDP_OUTLIER_CATALOGUE_PATH = _FIXTURE_DIR / "yahoo_2025_idp_outliers.json"
IDP_TOLERANCE = 1.0


@dataclass(frozen=True)
class OracleRecord:
    """One Yahoo-reported weekly fantasy-point total for one scoring entity."""

    entity_id: str
    season: int
    week: int
    unit: ScoringUnit
    yahoo_points: float
    label: str | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.entity_id, self.season, self.week)


# --------------------------------------------------------------------------- #
# Fixture (de)serialisation — pure, no I/O beyond the passed path.
#
# Both fixture files are a JSON list of records sharing the identity quartet
# (entity_id, season, week, unit) plus a label; only the payload field differs
# (``yahoo_points`` vs ``stats``). One read/write pair handles both, given a
# per-type row<->dict converter.
# --------------------------------------------------------------------------- #

Jsonable = dict[str, object]


def _identity(d: Jsonable) -> tuple[str, int, int, ScoringUnit, str | None]:
    return (
        str(d["entity_id"]),
        int(d["season"]),  # type: ignore[arg-type]
        int(d["week"]),  # type: ignore[arg-type]
        ScoringUnit(str(d["unit"])),
        (str(d["label"]) if d.get("label") is not None else None),
    )


def _sort_key(d: Jsonable) -> tuple[object, object, object]:
    return (d["unit"], d["entity_id"], d["week"])


def _write_fixture(items: Iterable[object], path: Path, to_json) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sorted((to_json(it) for it in items), key=_sort_key)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", newline="\n")
    return path


def _load_fixture(path: Path, from_json):
    return [from_json(d) for d in json.loads(path.read_text())]


def _oracle_to_json(r: OracleRecord) -> Jsonable:
    return {
        "entity_id": r.entity_id,
        "season": r.season,
        "week": r.week,
        "unit": r.unit.value,
        "yahoo_points": r.yahoo_points,
        "label": r.label,
    }


def _oracle_from_json(d: Jsonable) -> OracleRecord:
    entity_id, season, week, unit, label = _identity(d)
    return OracleRecord(
        entity_id=entity_id,
        season=season,
        week=week,
        unit=unit,
        yahoo_points=float(d["yahoo_points"]),  # type: ignore[arg-type]
        label=label,
    )


def _stat_row_to_json(row: StatRow) -> Jsonable:
    return {
        "entity_id": row.entity_id,
        "season": row.season,
        "week": row.week,
        "unit": row.unit.value,
        "stats": {k: float(v) for k, v in row.stats.items()},
        "label": row.label,
    }


def _stat_row_from_json(d: Jsonable) -> StatRow:
    entity_id, season, week, unit, label = _identity(d)
    allowed = STATS_BY_UNIT[unit]
    raw_stats = dict(d.get("stats") or {})  # type: ignore[arg-type]
    stats = {k: float(v) for k, v in raw_stats.items() if k in allowed}
    return StatRow(
        entity_id=entity_id, season=season, week=week, unit=unit, stats=stats, label=label
    )


def oracle_records_to_json(records: Iterable[OracleRecord]) -> list[Jsonable]:
    return [_oracle_to_json(r) for r in records]


def oracle_records_from_json(data: Sequence[Jsonable]) -> list[OracleRecord]:
    return [_oracle_from_json(d) for d in data]


def stat_rows_to_json(rows: Iterable[StatRow]) -> list[Jsonable]:
    return [_stat_row_to_json(row) for row in rows]


def stat_rows_from_json(data: Sequence[Jsonable]) -> list[StatRow]:
    return [_stat_row_from_json(d) for d in data]


def write_oracle_fixture(
    records: Iterable[OracleRecord], path: Path = ORACLE_FIXTURE_PATH
) -> Path:
    return _write_fixture(records, path, _oracle_to_json)


def load_oracle_fixture(path: Path = ORACLE_FIXTURE_PATH) -> list[OracleRecord]:
    return _load_fixture(path, _oracle_from_json)


def write_stat_rows_fixture(rows: Iterable[StatRow], path: Path = STAT_ROWS_FIXTURE_PATH) -> Path:
    return _write_fixture(rows, path, _stat_row_to_json)


def load_stat_rows_fixture(path: Path = STAT_ROWS_FIXTURE_PATH) -> list[StatRow]:
    return _load_fixture(path, _stat_row_from_json)


@dataclass(frozen=True)
class IdpOutlier:
    """One catalogued individual-defender player-week outside ``IDP_TOLERANCE``.

    ``engine_points`` / ``yahoo_points`` record the discrepancy as it stood when
    the entry was written; the IDP gate re-checks them against a fresh score and
    the oracle so a stale entry cannot linger. ``cause`` is a human sentence — an
    NFL gamebook vs. Yahoo scorer difference (solo vs. assisted tackle splits, a
    half-sack rounding, a TFL Yahoo did not credit), never "engine bug". A
    systematic offset across many weeks is a ruleset gap and is fixed in
    ``RIP_TIDE_RULESET`` instead of catalogued.
    """

    entity_id: str
    season: int
    week: int
    engine_points: float
    yahoo_points: float
    cause: str

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.entity_id, self.season, self.week)


def _idp_outlier_from_json(d: Jsonable) -> IdpOutlier:
    return IdpOutlier(
        entity_id=str(d["entity_id"]),
        season=int(d["season"]),  # type: ignore[arg-type]
        week=int(d["week"]),  # type: ignore[arg-type]
        engine_points=float(d["engine_points"]),  # type: ignore[arg-type]
        yahoo_points=float(d["yahoo_points"]),  # type: ignore[arg-type]
        cause=str(d["cause"]),
    )


def load_idp_outlier_catalogue(
    path: Path = IDP_OUTLIER_CATALOGUE_PATH,
) -> list[IdpOutlier]:
    return _load_fixture(path, _idp_outlier_from_json)


# --------------------------------------------------------------------------- #
# Box-score transform: raw Yahoo scrape -> (oracle records, stat rows).
#
# The raw file is ``{"<player name>|<week>": [yahoo_total, [[stat label, count],
# ...]]}``. Yahoo's stat labels are mapped to the engine's canonical keys here.
# --------------------------------------------------------------------------- #

# A team defense is entered under the team nickname; an individual defender is
# always a person's name. That is the only reliable split — IDP box scores carry
# "Sack", "Tackles for Loss" etc. too.
TEAM_NICKNAMES = frozenset(
    {
        "49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers",
        "Cardinals", "Chargers", "Chiefs", "Colts", "Commanders", "Cowboys",
        "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions",
        "Packers", "Panthers", "Patriots", "Raiders", "Rams", "Ravens", "Saints",
        "Seahawks", "Steelers", "Texans", "Titans", "Vikings",
    }
)

# Yahoo prints one "Points Allowed <band> points" line per team defense, except
# the 21-27 band (worth 0), which it omits. The engine takes an exact points-
# allowed count and buckets it, so map each band to a representative value.
_POINTS_ALLOWED_REP: Mapping[str, int] = {
    "Points Allowed 0 points": 0,
    "Points Allowed 1-6 points": 3,
    "Points Allowed 7-13 points": 10,
    "Points Allowed 14-20 points": 17,
    "Points Allowed 21-27 points": 24,
    "Points Allowed 28-34 points": 31,
    "Points Allowed 35+ points": 40,
}
_POINTS_ALLOWED_ABSENT = 24  # the omitted 21-27 band

# Individual-defense stats RIP TIDE scores for any player (offense/kicker too).
_IDP_SHARED: Mapping[str, str] = {
    "Tackle Solo": "tackle_solo",
    "Tackle Assist": "tackle_assist",
    "Pass Defended": "passes_defended",
}
_OFFENSE_LABELS: Mapping[str, str] = {
    "Passing Yards": "passing_yards",
    "Passing Touchdowns": "passing_touchdowns",
    "Interceptions": "interceptions_thrown",
    "Sacks": "sacks_taken",
    "Rushing Yards": "rushing_yards",
    "Rushing Touchdowns": "rushing_touchdowns",
    "Receiving Yards": "receiving_yards",
    "Receiving Touchdowns": "receiving_touchdowns",
    "2-Point Conversions": "two_point_conversions",
    "Return Yards": "return_yards",
    **_IDP_SHARED,
}
_KICKER_LABELS: Mapping[str, str] = {
    "Field Goals 0-19 Yards": "fg_made_0_19",
    "Field Goals 20-29 Yards": "fg_made_20_29",
    "Field Goals 30-39 Yards": "fg_made_30_39",
    "Field Goals 40-49 Yards": "fg_made_40_49",
    "Field Goals 50+ Yards": "fg_made_50_plus",
    "Field Goals Missed 0-19 Yards": "fg_missed_0_19",
    "Point After Attempt Made": "pat_made",
    "Point After Attempt Missed": "pat_missed",
    **_IDP_SHARED,
}
_TEAM_DEFENSE_LABELS: Mapping[str, str] = {
    "Sack": "sacks",
    "Interception": "interceptions",
    "Fumble Recovery": "fumble_recoveries",
    "Touchdown": "defensive_touchdowns",
    "Kickoff and Punt Return Touchdowns": "defensive_touchdowns",
    "Safety": "safeties",
    "Block Kick": "blocked_kicks",
    "Tackles for Loss": "tackles_for_loss",
    "Return Yards": "return_yards",
}
# The "D" slot. Yahoo prints an individual defender's INT/fumble-return yardage
# as "Turnover Return Yards" — its own canonical key ``turnover_return_yards``,
# kept apart from a returner's kick/punt ``return_yards``.
_INDIVIDUAL_DEFENSE_LABELS: Mapping[str, str] = {
    "Tackle Solo": "tackle_solo",
    "Tackle Assist": "tackle_assist",
    "Pass Defended": "passes_defended",
    "Sack": "sacks",
    "Interception": "interceptions",
    "Fumble Force": "forced_fumbles",
    "Fumble Recovery": "fumble_recoveries",
    "Touchdown": "defensive_touchdowns",
    "Kickoff and Punt Return Touchdowns": "defensive_touchdowns",
    "Safety": "safeties",
    "Block Kick": "blocked_kicks",
    "Tackles for Loss": "tackles_for_loss",
    "Turnover Return Yards": "turnover_return_yards",
}
_LABELS_BY_UNIT: Mapping[ScoringUnit, Mapping[str, str]] = {
    ScoringUnit.OFFENSE: _OFFENSE_LABELS,
    ScoringUnit.KICKER: _KICKER_LABELS,
    ScoringUnit.TEAM_DEFENSE: _TEAM_DEFENSE_LABELS,
    ScoringUnit.INDIVIDUAL_DEFENSE: _INDIVIDUAL_DEFENSE_LABELS,
}

# Labels that only an offensive player accrues (a tackle or return-yard line
# does not distinguish offense from defense).
_OFFENSE_MARKERS = frozenset(
    {
        "Passing Yards", "Passing Touchdowns", "Rushing Yards", "Rushing Touchdowns",
        "Receiving Yards", "Receiving Touchdowns", "2-Point Conversions", "Interceptions",
    }
)


class UnmappedStatLabelError(ValueError):
    """A raw box score used a Yahoo stat label the transform does not recognise."""


def _classify(name: str, labels: set[str]) -> ScoringUnit:
    """Which scoring unit a box-score line belongs to.

    Team defense by nickname; kicker by a field-goal / PAT line; offense by an
    offensive stat (or a bare returner line for someone rostered on offense);
    everything else — tackles, sacks, takeaways with no offensive stat — is a
    pure individual defender, the "D" slot.
    """
    if name in TEAM_NICKNAMES:
        return ScoringUnit.TEAM_DEFENSE
    if any(label.startswith(("Field Goal", "Point After")) for label in labels):
        return ScoringUnit.KICKER
    if labels & _OFFENSE_MARKERS:
        return ScoringUnit.OFFENSE
    if "Return Yards" in labels and labels <= {"Return Yards", *_IDP_SHARED}:
        return ScoringUnit.OFFENSE  # a returner rostered on offense, no box stats
    return ScoringUnit.INDIVIDUAL_DEFENSE


def records_from_box_scores(
    raw: Mapping[str, Sequence], *, season: int = ORACLE_SEASON
) -> tuple[list[OracleRecord], list[StatRow]]:
    """Turn the raw box-score scrape into aligned oracle records and stat rows.

    Both lists are keyed by ``(player/team name, season, week)`` and cover every
    row in the scrape — offense, kicker, team DEF, and individual defender.
    Raises ``UnmappedStatLabelError`` if a Yahoo label has no canonical mapping —
    that means the scrape widened into territory the engine does not cover yet.
    """
    oracle: list[OracleRecord] = []
    stat_rows: list[StatRow] = []

    for key, (total, lines) in raw.items():
        name, week_str = key.rsplit("|", 1)
        week = int(week_str)
        labels = {str(label) for label, _ in lines}
        unit = _classify(name, labels)

        label_map = _LABELS_BY_UNIT[unit]
        stats: dict[str, float] = {}
        for label, count in lines:
            label = str(label)
            if unit is ScoringUnit.TEAM_DEFENSE and label in _POINTS_ALLOWED_REP:
                stats["points_allowed"] = float(_POINTS_ALLOWED_REP[label])
                continue
            canonical = label_map.get(label)
            if canonical is None:
                raise UnmappedStatLabelError(
                    f"{unit.value}: {name} wk{week}: unmapped Yahoo label {label!r}"
                )
            stats[canonical] = stats.get(canonical, 0.0) + float(count)

        if unit is ScoringUnit.TEAM_DEFENSE and "points_allowed" not in stats:
            stats["points_allowed"] = float(_POINTS_ALLOWED_ABSENT)

        oracle.append(
            OracleRecord(name, season, week, unit, round(float(total), 2), label=name)
        )
        stat_rows.append(StatRow(name, season, week, unit, stats, label=name))

    oracle.sort(key=lambda r: (r.unit.value, r.entity_id, r.week))
    stat_rows.sort(key=lambda r: (r.unit.value, r.entity_id, r.week))
    return oracle, stat_rows


def load_box_scores(path: Path = BOX_SCORE_RAW_PATH) -> dict[str, list]:
    return json.loads(path.read_text())


def build_fixtures(
    raw_path: Path = BOX_SCORE_RAW_PATH,
    *,
    oracle_path: Path = ORACLE_FIXTURE_PATH,
    stat_rows_path: Path = STAT_ROWS_FIXTURE_PATH,
) -> tuple[list[OracleRecord], list[StatRow]]:
    """Read the raw scrape, write both gate fixtures, return what was written."""
    oracle, stat_rows = records_from_box_scores(load_box_scores(raw_path))
    write_oracle_fixture(oracle, oracle_path)
    write_stat_rows_fixture(stat_rows, stat_rows_path)
    return oracle, stat_rows


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m deadparrots.scoring.oracle",
        description="Rebuild the 2025 scoring golden fixtures from the Yahoo box-score scrape.",
    )
    parser.add_argument("command", choices=["build"], help="build: raw scrape -> gate fixtures")
    parser.add_argument("--raw", type=Path, default=BOX_SCORE_RAW_PATH)
    args = parser.parse_args(argv)

    oracle, stat_rows = build_fixtures(args.raw)
    by_unit: dict[str, int] = {}
    for r in oracle:
        by_unit[r.unit.value] = by_unit.get(r.unit.value, 0) + 1
    print(f"wrote {len(oracle)} oracle records + {len(stat_rows)} stat rows")
    for unit, count in sorted(by_unit.items()):
        print(f"  {unit}: {count}")
    print("\nRun `uv run pytest -m gate -v` to check the engine against them.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
