from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..scoring import round_points
from .roster import Lineup, RosterPlayer
from .slots import RIP_TIDE_SLOTS, LineupSlots, assign_slots

# Gap drivers (CONTEXT.md): the additive per-roster-slot decomposition of
# ``E[Dead Parrots] − E[opponent]``. Expected weekly points are additive across
# a lineup and unaffected by the correlation model, so aligning the two lineups
# slot-for-slot and differencing the slot means gives a decomposition that sums
# *exactly* to the total expected-points difference (issue #11 acceptance
# criterion 4).

__all__ = [
    "GapDriver",
    "gap_drivers",
    "total_expected_gap",
]


@dataclass(frozen=True)
class GapDriver:
    """One slot's share of the expected-points gap.

    ``contribution`` is ``dead_parrots_mean − opponent_mean`` for this slot,
    carried unrounded so the drivers sum cleanly; ``*_rounded`` fields are for
    display. A positive value is a slot Dead Parrots win on projection.
    """

    slot: str
    dead_parrots_player: str
    opponent_player: str
    dead_parrots_mean: float
    opponent_mean: float
    contribution: float

    @property
    def dead_parrots_mean_rounded(self) -> float:
        return round_points(self.dead_parrots_mean)

    @property
    def opponent_mean_rounded(self) -> float:
        return round_points(self.opponent_mean)

    @property
    def contribution_rounded(self) -> float:
        return round_points(self.contribution)


def _slotted(
    players: Sequence[RosterPlayer], slots: LineupSlots
) -> list[tuple[str, RosterPlayer]]:
    """Assign a lineup to its slots, then order players within each same-name
    slot by projection (highest first) so the pairing is stable — RB1 is the
    higher-projected back on each side, not whichever the matcher happened to
    place first."""
    assignment = assign_slots(players, slots)
    if assignment is None:
        raise ValueError("lineup is not legal for these slots")
    by_slot: dict[str, list[RosterPlayer]] = {}
    for slot_name, player in assignment:
        by_slot.setdefault(slot_name, []).append(player)
    ordered: list[tuple[str, RosterPlayer]] = []
    for rule in slots.rules:
        bucket = by_slot.get(rule.name, [])
        bucket.sort(key=lambda p: p.sim.mean, reverse=True)
        ordered.extend((rule.name, player) for player in bucket)
    return ordered


def gap_drivers(
    dead_parrots: Lineup,
    opponent: Sequence[RosterPlayer],
    *,
    slots: LineupSlots = RIP_TIDE_SLOTS,
) -> tuple[GapDriver, ...]:
    """Per-slot decomposition of ``E[Dead Parrots] − E[opponent]``.

    Both lineups must be legal for ``slots`` (they field the same slots, so the
    two slot sequences line up one-to-one). The returned tuple is in slot
    display order; ``math.fsum(d.contribution for d in result)`` equals
    ``Σ dead-parrots means − Σ opponent means`` to full precision.
    """
    dp_slotted = _slotted(list(dead_parrots.players), slots)
    opp_slotted = _slotted(list(opponent), slots)

    drivers: list[GapDriver] = []
    for (slot_name, dp_player), (_, opp_player) in zip(dp_slotted, opp_slotted):
        dp_mean = dp_player.sim.mean
        opp_mean = opp_player.sim.mean
        drivers.append(
            GapDriver(
                slot=slot_name,
                dead_parrots_player=dp_player.name,
                opponent_player=opp_player.name,
                dead_parrots_mean=dp_mean,
                opponent_mean=opp_mean,
                contribution=dp_mean - opp_mean,
            )
        )
    return tuple(drivers)


def total_expected_gap(drivers: Sequence[GapDriver]) -> float:
    """The expected-points difference the drivers decompose, summed exactly."""
    return math.fsum(driver.contribution for driver in drivers)
