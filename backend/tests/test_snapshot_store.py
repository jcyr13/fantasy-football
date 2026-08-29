"""Issue #17: the weekly-snapshot store is append-only — a re-capture for a
week that already has a snapshot never overwrites it, and a second outcome
backfill is refused (ADR-0014 §2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deadparrots.snapshot import (
    PlayerActual,
    SnapshotOutcome,
    WeeklySnapshot,
    get_outcome,
    get_record,
    get_snapshot,
    list_records,
    save_outcome,
    save_snapshot,
    snapshot_id_for,
)


def _snapshot(season: int, week: int, *, recommended: list[dict] | None = None) -> WeeklySnapshot:
    captured = {
        "weekly": {
            "season": season,
            "week": week,
            "recommended_lineup": recommended
            or [{"player_id": "p1", "name": "Player One", "mean": 12.5}],
        },
        "team_outlook": {"week": week},
        "trade_desk": {"week": week},
        "free_agents": {"week": week},
    }
    return WeeklySnapshot(
        snapshot_id=snapshot_id_for(season, week),
        season=season,
        week=week,
        created_at=datetime(2026, 9, 24, 15, 0, tzinfo=UTC),
        rng_seed=123,
        captured=captured,
    )


def _outcome(snapshot_id: str, *, dp: float, opp: float) -> SnapshotOutcome:
    return SnapshotOutcome(
        snapshot_id=snapshot_id,
        backfilled_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
        dead_parrots_total=dp,
        opponent_total=opp,
        result="win" if dp > opp else "loss" if dp < opp else "tie",
        player_actuals=[PlayerActual("p1", "Player One", 12.5, 18.0)],
    )


def test_save_and_read_back_round_trips(sqlite_conn):
    snap = _snapshot(2026, 3)
    stored, created = save_snapshot(sqlite_conn, snap)
    assert created is True
    assert stored.snapshot_id == "2026-3"
    assert stored.captured["weekly"]["week"] == 3

    got = get_snapshot(sqlite_conn, 2026, 3)
    assert got is not None
    assert got.rng_seed == 123
    assert got.created_at == snap.created_at


def test_recapture_for_the_same_week_does_not_overwrite(sqlite_conn):
    original, created = save_snapshot(sqlite_conn, _snapshot(2026, 3))
    assert created is True

    # A re-run with different numbers for the same (season, week).
    mutated = _snapshot(
        2026, 3, recommended=[{"player_id": "pX", "name": "Different", "mean": 99.0}]
    )
    stored, created_again = save_snapshot(sqlite_conn, mutated)

    assert created_again is False
    assert stored.captured == original.captured
    assert stored.captured["weekly"]["recommended_lineup"][0]["player_id"] == "p1"

    # And only one row exists.
    assert len(list_records(sqlite_conn, season=2026)) == 1


def test_outcome_backfills_onto_its_own_row_and_is_one_shot(sqlite_conn):
    save_snapshot(sqlite_conn, _snapshot(2026, 3))
    sid = snapshot_id_for(2026, 3)

    assert save_outcome(sqlite_conn, _outcome(sid, dp=140.0, opp=120.0)) is True
    got = get_outcome(sqlite_conn, sid)
    assert got is not None
    assert got.result == "win"
    assert got.player_actuals[0].actual_points == 18.0

    # A second backfill is refused; the first stands.
    assert save_outcome(sqlite_conn, _outcome(sid, dp=1.0, opp=999.0)) is False
    assert get_outcome(sqlite_conn, sid).dead_parrots_total == 140.0

    # The capture row is untouched by the backfill.
    assert get_snapshot(sqlite_conn, 2026, 3).captured["weekly"]["week"] == 3


def test_get_record_pairs_snapshot_with_outcome(sqlite_conn):
    save_snapshot(sqlite_conn, _snapshot(2026, 3))
    rec = get_record(sqlite_conn, 2026, 3)
    assert rec is not None and rec.scored is False

    save_outcome(sqlite_conn, _outcome(snapshot_id_for(2026, 3), dp=100.0, opp=110.0))
    rec = get_record(sqlite_conn, 2026, 3)
    assert rec.scored is True
    assert rec.outcome.result == "loss"


def test_list_records_is_newest_week_first_and_season_scoped(sqlite_conn):
    for wk in (1, 2, 3):
        save_snapshot(sqlite_conn, _snapshot(2026, wk))
    save_snapshot(sqlite_conn, _snapshot(2025, 14))

    all_2026 = list_records(sqlite_conn, season=2026)
    assert [r.snapshot.week for r in all_2026] == [3, 2, 1]

    every = list_records(sqlite_conn)
    assert (every[0].snapshot.season, every[0].snapshot.week) == (2026, 3)
    assert (every[-1].snapshot.season, every[-1].snapshot.week) == (2025, 14)


def test_missing_week_reads_back_as_none(sqlite_conn):
    assert get_snapshot(sqlite_conn, 2026, 9) is None
    assert get_record(sqlite_conn, 2026, 9) is None
    assert list_records(sqlite_conn) == []


@pytest.mark.parametrize(
    ("dp", "opp", "expected"),
    [(140.0, 120.0, "win"), (100.0, 130.0, "loss"), (111.0, 111.0, "tie")],
)
def test_result_round_trips_through_the_check_constraint(sqlite_conn, dp, opp, expected):
    save_snapshot(sqlite_conn, _snapshot(2026, 5))
    sid = snapshot_id_for(2026, 5)
    save_outcome(sqlite_conn, _outcome(sid, dp=dp, opp=opp))
    assert get_outcome(sqlite_conn, sid).result == expected
