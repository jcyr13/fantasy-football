from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .rows import STATS_BY_UNIT, ScoringUnit, StatRow

# The 2025 validation "oracle": real Yahoo per-player weekly fantasy points for
# the RIP TIDE League, captured once via ``yfpy`` and frozen as golden fixtures.
# The scoring engine is not trusted until its output reproduces these exactly
# for every offense / kicker / team-DEF player-week (spec issue #1).
#
# This module is a one-off capture tool and fixture (de)serialiser. It is the
# ONLY file in ``deadparrots.scoring`` that touches the network or disk; the
# engine never imports it. ``yfpy`` / ``duckdb`` are imported lazily so the
# package has no hard dependency on them.
#
# Run:  python -m deadparrots.scoring.oracle --help
# Docs: docs/scoring-oracle-capture.md

RIP_TIDE_LEAGUE_ID = 735806
ORACLE_SEASON = 2025

# Default fixture locations, relative to the backend package root.
_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scoring"
ORACLE_FIXTURE_PATH = _FIXTURE_DIR / "yahoo_2025_oracle.json"
STAT_ROWS_FIXTURE_PATH = _FIXTURE_DIR / "nflverse_2025_stat_rows.json"


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
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


# --------------------------------------------------------------------------- #
# Yahoo capture — network. Lazy ``yfpy`` import; not covered by unit tests.
# --------------------------------------------------------------------------- #

_OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE"}


def capture_oracle_records(
    *,
    league_id: int = RIP_TIDE_LEAGUE_ID,
    season: int = ORACLE_SEASON,
    weeks: Iterable[int] = range(1, 18),
    yahoo_consumer_key: str | None = None,
    yahoo_consumer_secret: str | None = None,
    auth_dir: Path | None = None,
) -> list[OracleRecord]:
    """Pull every rostered player's weekly fantasy-point total for ``season``.

    Uses ``yfpy``; credentials come from the arguments or, if omitted, from
    ``yfpy``'s own ``YAHOO_CONSUMER_KEY`` / ``YAHOO_CONSUMER_SECRET`` env vars
    and cached OAuth token in ``auth_dir`` (default: the current directory).

    Kicker rows are tagged ``KICKER``; team-defense rows (Yahoo position ``DEF``)
    are tagged ``TEAM_DEFENSE`` with the editorial team abbreviation as the
    entity id; everything else with an offensive position is ``OFFENSE``.
    Players whose Yahoo position is none of those (IDP "D" slot) are skipped —
    that surface is a separate ticket.
    """
    from yfpy.query import YahooFantasySportsQuery  # type: ignore[import-untyped]

    query = YahooFantasySportsQuery(
        league_id=str(league_id),
        game_code="nfl",
        game_id=None,
        yahoo_consumer_key=yahoo_consumer_key,
        yahoo_consumer_secret=yahoo_consumer_secret,
        env_file_location=auth_dir,
        save_token_data_to_env_file=bool(auth_dir),
    )

    teams = query.get_league_teams()
    records: dict[tuple[str, int, int], OracleRecord] = {}

    for week in weeks:
        for team in teams:
            roster = query.get_team_roster_player_stats_by_week(team.team_id, chosen_week=week)
            for player in roster:
                unit = _yahoo_unit(player)
                if unit is None:
                    continue
                points = getattr(getattr(player, "player_points", None), "total", None)
                if points is None:
                    continue
                entity_id = _yahoo_entity_id(player, unit)
                rec = OracleRecord(
                    entity_id=entity_id,
                    season=season,
                    week=int(week),
                    unit=unit,
                    yahoo_points=round(float(points), 2),
                    label=getattr(player, "full_name", None) or entity_id,
                )
                records[rec.key] = rec

    return sorted(records.values(), key=lambda r: (r.unit.value, r.entity_id, r.week))


def _yahoo_unit(player: object) -> ScoringUnit | None:
    position = (
        getattr(player, "primary_position", None)
        or getattr(player, "display_position", None)
        or ""
    ).upper()
    if position == "K":
        return ScoringUnit.KICKER
    if position in {"DEF", "DST"}:
        return ScoringUnit.TEAM_DEFENSE
    if position in _OFFENSE_POSITIONS:
        return ScoringUnit.OFFENSE
    return None


def _yahoo_entity_id(player: object, unit: ScoringUnit) -> str:
    if unit is ScoringUnit.TEAM_DEFENSE:
        abbr = getattr(player, "editorial_team_abbr", None)
        if abbr:
            return str(abbr).upper()
    return str(getattr(player, "player_id", "") or getattr(player, "player_key", ""))


def build_offense_kicker_stat_rows(
    parquet_path: Path, *, season: int = ORACLE_SEASON
) -> list[StatRow]:
    """Read an nflverse ``player_stats`` parquet and return offense + kicker rows.

    This is the mechanical half of the stat-row fixture. Team-defense rows are
    rolled up from play-by-play separately and appended by the capture operator
    (docs/scoring-oracle-capture.md); ``entity_id`` here is the nflverse
    ``player_id``, which the operator must reconcile with the Yahoo-keyed oracle.
    """
    import polars as pl

    from .adapters import stat_rows_from_player_stats

    frame = pl.read_parquet(parquet_path)
    if "season" in frame.columns:
        frame = frame.filter(pl.col("season") == season)
    return stat_rows_from_player_stats(frame.iter_rows(named=True))


def _summarise(rows: Sequence[object], path: Path, kind: str) -> None:
    by_unit: dict[str, int] = {}
    for row in rows:
        unit = row.unit.value  # type: ignore[attr-defined]
        by_unit[unit] = by_unit.get(unit, 0) + 1
    print(f"wrote {len(rows)} {kind} to {path}")
    for unit, count in sorted(by_unit.items()):
        print(f"  {unit}: {count}")


def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m deadparrots.scoring.oracle",
        description="Build the 2025 scoring golden fixtures (spec issue #1 validation gate).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="pull the Yahoo oracle (needs yfpy + OAuth)")
    cap.add_argument("--league-id", type=int, default=RIP_TIDE_LEAGUE_ID)
    cap.add_argument("--season", type=int, default=ORACLE_SEASON)
    cap.add_argument(
        "--auth-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory holding the yfpy .env / token file (default: cwd).",
    )
    cap.add_argument("--out", type=Path, default=ORACLE_FIXTURE_PATH)

    rows = sub.add_parser(
        "build-rows",
        help="build the offense+kicker stat rows from a cached nflverse player_stats parquet",
    )
    rows.add_argument("parquet", type=Path, help="path to a player_stats.parquet in the cache")
    rows.add_argument("--season", type=int, default=ORACLE_SEASON)
    rows.add_argument("--out", type=Path, default=STAT_ROWS_FIXTURE_PATH)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.command == "capture":
        records = capture_oracle_records(
            league_id=args.league_id,
            season=args.season,
            auth_dir=args.auth_dir,
        )
        path = write_oracle_fixture(records, args.out)
        _summarise(records, path, "oracle records")
        print(
            "\nNext: `build-rows` for the offense+kicker stat rows, then append the "
            "team-defense roll-up — see docs/scoring-oracle-capture.md."
        )
        return 0

    if args.command == "build-rows":
        rows = build_offense_kicker_stat_rows(args.parquet, season=args.season)
        path = write_stat_rows_fixture(rows, args.out)
        _summarise(rows, path, "stat rows")
        print(
            "\nThis is offense + kicker only. Append the team-defense rows "
            "(deadparrots.scoring.adapters.team_defense_stat_row) before running the gate."
        )
        return 0

    return 2  # pragma: no cover — argparse rejects an unknown command first


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
