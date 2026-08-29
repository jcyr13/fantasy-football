from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# The persisted per-week record (issue #17; ADR-0014). ``WeeklySnapshot`` is the
# immutable capture — projections, lineups, recommendations and strategic-layer
# outputs frozen as the four screen contracts (ADR-0014 §1). ``SnapshotOutcome``
# is the append-only backfill of what actually happened; it lives in its own
# table so the capture row is never mutated.

__all__ = [
    "GameResult",
    "PlayerActual",
    "SnapshotOutcome",
    "SnapshotRecord",
    "WeeklySnapshot",
    "snapshot_id_for",
]

GameResult = Literal["win", "loss", "tie"]


def snapshot_id_for(season: int, week: int) -> str:
    """The stable id for a week's snapshot — the same string
    :func:`deadparrots.simulation.seed_from_snapshot_id` keys the sim off."""
    return f"{season}-{week}"


@dataclass(frozen=True)
class WeeklySnapshot:
    """One week's immutable capture.

    ``captured`` is the JSON of ``GET /api/weekly`` + ``/api/team-outlook`` +
    ``/api/trade-desk`` + ``/api/free-agents`` for the week, keyed
    ``weekly`` / ``team_outlook`` / ``trade_desk`` / ``free_agents``
    (ADR-0014 §1). Nothing here is rewritten after the first capture.
    """

    snapshot_id: str
    season: int
    week: int
    created_at: datetime
    rng_seed: int
    captured: Mapping[str, object]


@dataclass(frozen=True)
class PlayerActual:
    """One frozen-lineup player's model projection next to what he scored."""

    player_id: str
    name: str
    projected_points: float
    actual_points: float

    @property
    def delta(self) -> float:
        """Actual minus projected — positive when the player beat the model."""
        return self.actual_points - self.projected_points


@dataclass(frozen=True)
class SnapshotOutcome:
    """What actually happened, backfilled onto a snapshot after games.

    Written once into its own table; a second backfill for the same week does
    not overwrite this (ADR-0014 §2).
    """

    snapshot_id: str
    backfilled_at: datetime
    dead_parrots_total: float
    opponent_total: float
    result: GameResult
    player_actuals: Sequence[PlayerActual]


@dataclass(frozen=True)
class SnapshotRecord:
    """A snapshot with its outcome, if the week has been scored yet."""

    snapshot: WeeklySnapshot
    outcome: SnapshotOutcome | None

    @property
    def scored(self) -> bool:
        return self.outcome is not None
