"""Issue #17: ``build_outcome`` is the pure join of the week's finals and
per-player actuals onto the frozen recommended lineup (ADR-0014 §3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deadparrots.snapshot import WeeklySnapshot, build_outcome, snapshot_id_for


def _snapshot(recommended: list[dict]) -> WeeklySnapshot:
    return WeeklySnapshot(
        snapshot_id=snapshot_id_for(2026, 3),
        season=2026,
        week=3,
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
        rng_seed=1,
        captured={"weekly": {"recommended_lineup": recommended}},
    )


RECOMMENDED = [
    {"player_id": "qb1", "name": "Josh Allen", "mean": 22.0},
    {"player_id": "rb1", "name": "Bijan Robinson", "mean": 15.5},
    {"player_id": "wr1", "name": "Ja'Marr Chase", "mean": 17.0},
]


def test_result_and_totals_are_derived_from_the_two_finals():
    out = build_outcome(
        _snapshot(RECOMMENDED),
        dead_parrots_total=138.4,
        opponent_total=120.1,
        player_actuals={},
    )
    assert out.result == "win"
    assert out.dead_parrots_total == 138.4
    assert out.opponent_total == 120.1
    assert out.snapshot_id == "2026-3"


@pytest.mark.parametrize(
    ("dp", "opp", "expected"),
    [(120.0, 130.0, "loss"), (130.0, 120.0, "win"), (125.5, 125.5, "tie")],
)
def test_result_covers_win_loss_tie(dp, opp, expected):
    out = build_outcome(
        _snapshot(RECOMMENDED),
        dead_parrots_total=dp,
        opponent_total=opp,
        player_actuals={},
    )
    assert out.result == expected


def test_actuals_join_onto_every_frozen_lineup_slot():
    out = build_outcome(
        _snapshot(RECOMMENDED),
        dead_parrots_total=100.0,
        opponent_total=90.0,
        player_actuals={"qb1": 30.0, "rb1": 4.0},
    )
    by_id = {p.player_id: p for p in out.player_actuals}
    assert set(by_id) == {"qb1", "rb1", "wr1"}
    # projection mean is carried from the snapshot, actual from the mapping
    assert by_id["qb1"].projected_points == 22.0
    assert by_id["qb1"].actual_points == 30.0
    assert by_id["qb1"].delta == pytest.approx(8.0)
    # a player omitted from the mapping (did not play) scores 0.0
    assert by_id["wr1"].actual_points == 0.0
    assert by_id["wr1"].delta == pytest.approx(-17.0)


def test_yahoo_set_lineup_players_are_joined_too():
    snap = WeeklySnapshot(
        snapshot_id=snapshot_id_for(2026, 3),
        season=2026,
        week=3,
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
        rng_seed=1,
        captured={
            "weekly": {
                "recommended_lineup": RECOMMENDED,
                # a player John started that the model did not recommend
                "dead_parrots_current_lineup": [
                    {"player_id": "te1", "name": "Bench Guy", "mean": 6.0}
                ],
            }
        },
    )
    out = build_outcome(
        snap,
        dead_parrots_total=100.0,
        opponent_total=90.0,
        player_actuals={"te1": 14.0},
    )
    by_id = {p.player_id: p for p in out.player_actuals}
    assert set(by_id) == {"qb1", "rb1", "wr1", "te1"}
    assert by_id["te1"].projected_points == 6.0
    assert by_id["te1"].actual_points == 14.0


def test_a_submitted_id_in_no_frozen_lineup_is_still_kept():
    out = build_outcome(
        _snapshot(RECOMMENDED),
        dead_parrots_total=100.0,
        opponent_total=90.0,
        player_actuals={"latepickup": 9.0},
    )
    by_id = {p.player_id: p for p in out.player_actuals}
    assert "latepickup" in by_id
    assert by_id["latepickup"].projected_points == 0.0
    assert by_id["latepickup"].actual_points == 9.0


def test_backfilled_at_is_honoured_when_supplied():
    when = datetime(2026, 9, 30, 8, 30, tzinfo=UTC)
    out = build_outcome(
        _snapshot(RECOMMENDED),
        dead_parrots_total=1.0,
        opponent_total=2.0,
        player_actuals={},
        backfilled_at=when,
    )
    assert out.backfilled_at == when


def test_no_frozen_lineups_and_no_actuals_yields_no_player_rows():
    out = build_outcome(
        _snapshot([]),
        dead_parrots_total=100.0,
        opponent_total=100.0,
        player_actuals={},
    )
    assert out.player_actuals == []
    assert out.result == "tie"
