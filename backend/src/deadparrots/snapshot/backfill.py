from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from .models import GameResult, PlayerActual, SnapshotOutcome, WeeklySnapshot

# The pure half of the outcome backfill (ADR-0014 §3). ``build_outcome`` turns
# the week's two finals plus a ``{player_id: actual_points}`` mapping into a
# :class:`SnapshotOutcome`, joining the actuals onto the lineups the snapshot
# froze — the model's recommendation *and* the Yahoo-set lineup John actually
# started — so the History screen can show model-said next to what-happened per
# player, and whether deviating from the model helped. No I/O — where the
# numbers come from (a form body in v1, a post-games nflverse pull later) is the
# caller's concern.

__all__ = [
    "build_outcome",
    "current_lineup_players",
    "recommended_lineup_players",
]


def _result(dead_parrots_total: float, opponent_total: float) -> GameResult:
    if dead_parrots_total > opponent_total:
        return "win"
    if dead_parrots_total < opponent_total:
        return "loss"
    return "tie"


def _lineup_players(
    snapshot: WeeklySnapshot, key: str
) -> list[tuple[str, str, float]]:
    """``(player_id, name, projected_mean)`` for each player in the ``weekly``
    payload's ``key`` slot list, in slot order."""
    weekly = snapshot.captured.get("weekly")
    if not isinstance(weekly, Mapping):
        return []
    slots = weekly.get(key)
    if not isinstance(slots, (list, tuple)):
        return []
    out: list[tuple[str, str, float]] = []
    for slot in slots:
        if not isinstance(slot, Mapping):
            continue
        pid = slot.get("player_id")
        if not isinstance(pid, str):
            continue
        name = slot.get("name")
        out.append(
            (
                pid,
                name if isinstance(name, str) else "",
                float(slot.get("mean", 0.0) or 0.0),
            )
        )
    return out


def recommended_lineup_players(
    snapshot: WeeklySnapshot,
) -> list[tuple[str, str, float]]:
    """``(player_id, name, projected_mean)`` for the snapshot's recommended
    lineup."""
    return _lineup_players(snapshot, "recommended_lineup")


def current_lineup_players(
    snapshot: WeeklySnapshot,
) -> list[tuple[str, str, float]]:
    """``(player_id, name, projected_mean)`` for the Yahoo-set lineup the
    snapshot froze (empty when it was not a legal ten)."""
    return _lineup_players(snapshot, "dead_parrots_current_lineup")


def build_outcome(
    snapshot: WeeklySnapshot,
    *,
    dead_parrots_total: float,
    opponent_total: float,
    player_actuals: Mapping[str, float],
    backfilled_at: datetime | None = None,
) -> SnapshotOutcome:
    """Assemble the immutable outcome for ``snapshot``.

    ``result`` is derived from the two totals. ``player_actuals`` maps a
    Dead Parrots ``player_id`` to the RIP TIDE points he actually scored. A
    :class:`PlayerActual` row is emitted for every player in the frozen
    recommended lineup, every player in the frozen Yahoo-set lineup, and any
    other ``player_id`` the mapping carries (so a real starter the model did not
    pick is never silently dropped). A player the mapping omits scores 0.0; a
    ``player_id`` with no frozen projection carries 0.0 projected.
    """
    frozen: dict[str, tuple[str, float]] = {}
    for pid, name, projected in (
        *recommended_lineup_players(snapshot),
        *current_lineup_players(snapshot),
    ):
        frozen.setdefault(pid, (name, projected))
    for pid in player_actuals:
        frozen.setdefault(pid, ("", 0.0))

    actuals = [
        PlayerActual(
            player_id=pid,
            name=name,
            projected_points=projected,
            actual_points=float(player_actuals.get(pid, 0.0)),
        )
        for pid, (name, projected) in frozen.items()
    ]
    return SnapshotOutcome(
        snapshot_id=snapshot.snapshot_id,
        backfilled_at=backfilled_at or datetime.now(UTC),
        dead_parrots_total=float(dead_parrots_total),
        opponent_total=float(opponent_total),
        result=_result(float(dead_parrots_total), float(opponent_total)),
        player_actuals=actuals,
    )
