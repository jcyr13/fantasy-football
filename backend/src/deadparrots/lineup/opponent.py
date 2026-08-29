from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .roster import RosterPlayer, enumerate_lineups
from .slots import RIP_TIDE_SLOTS, LineupSlots, is_legal_lineup

# Building the opponent's likely starting lineup (CONTEXT.md "Opponent likely
# lineup", spec user story 3). Order of preference:
#
#   1. "yahoo-set"          — the lineup Yahoo already shows the opponent
#                             starting, when it is complete, legal, and healthy.
#   2. "prior-week-heuristic" — last week's starters, minus anyone unavailable
#                             (injured out / bye) and with obvious bench
#                             upgrades applied. NEVER their optimal lineup.
#   3. "projection-heuristic" — no set lineup and no prior week to lean on: the
#                             opponent is *assumed* to start their
#                             highest-projected legal lineup from available
#                             players. A stated fallback, not a claim they play
#                             optimally.
#
# Whichever is used is surfaced on the result, with notes recording every
# substitution the heuristic made.

__all__ = [
    "OpponentAssumption",
    "OpponentLineup",
    "build_opponent_lineup",
]

OpponentAssumption = Literal[
    "yahoo-set", "prior-week-heuristic", "projection-heuristic"
]

# A bench player must out-project the starter by at least this many points to be
# an "obvious" upgrade. A placeholder magnitude — roughly a positional tier of
# weekly scoring — pinned by behaviour, not calibration, like the sim's
# correlation shares (ADR-0007).
DEFAULT_UPGRADE_MARGIN = 3.0


@dataclass(frozen=True)
class OpponentLineup:
    """The opponent's assumed starters and how they were arrived at."""

    players: tuple[RosterPlayer, ...]
    assumption: OpponentAssumption
    notes: tuple[str, ...]

    @property
    def player_ids(self) -> frozenset[str]:
        return frozenset(p.player_id for p in self.players)


def _role_counts(players: Sequence[RosterPlayer]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for player in players:
        counts[player.role] = counts.get(player.role, 0) + 1
    return counts


def _can_extend_to_legal(
    partial: Sequence[RosterPlayer],
    bench: Sequence[RosterPlayer],
    slots: LineupSlots,
) -> bool:
    """Is there a legal lineup that keeps every player in ``partial`` and adds
    only players from ``bench``?"""
    if len(partial) > slots.size:
        return False
    partial_counts = _role_counts(partial)
    bench_counts = _role_counts(bench)
    for distribution in slots.role_count_distributions():
        if any(role not in distribution for role in partial_counts):
            continue
        if all(
            partial_counts.get(role, 0) <= target
            and target - partial_counts.get(role, 0) <= bench_counts.get(role, 0)
            for role, target in distribution.items()
        ):
            return True
    return False


def _best_projection_lineup(
    players: Sequence[RosterPlayer], slots: LineupSlots
) -> list[RosterPlayer] | None:
    best: list[RosterPlayer] | None = None
    best_points = float("-inf")
    for lineup in enumerate_lineups(players, slots):
        points = sum(p.sim.mean for p in lineup.players)
        if points > best_points:
            best_points = points
            best = list(lineup.players)
    return best


def _fill_to_legal(
    kept: Sequence[RosterPlayer],
    bench: Sequence[RosterPlayer],
    slots: LineupSlots,
    notes: list[str],
) -> list[RosterPlayer] | None:
    lineup = list(kept)
    bench_pool = sorted(bench, key=lambda p: p.sim.mean, reverse=True)
    for candidate in bench_pool:
        if is_legal_lineup(lineup, slots):
            break
        if any(p.player_id == candidate.player_id for p in lineup):
            continue
        trial = [*lineup, candidate]
        remaining = [
            b
            for b in bench_pool
            if all(p.player_id != b.player_id for p in trial)
        ]
        if _can_extend_to_legal(trial, remaining, slots):
            lineup.append(candidate)
            notes.append(
                f"Filled an open slot with {candidate.name} "
                f"(projected {candidate.sim.mean:.1f})."
            )
    return lineup if is_legal_lineup(lineup, slots) else None


def _apply_obvious_upgrades(
    lineup: list[RosterPlayer],
    roster: Sequence[RosterPlayer],
    slots: LineupSlots,
    upgrade_margin: float,
    notes: list[str],
) -> list[RosterPlayer]:
    while True:
        starting_ids = {p.player_id for p in lineup}
        bench = [
            p
            for p in roster
            if p.available and p.player_id not in starting_ids
        ]
        best_swap: tuple[float, RosterPlayer, RosterPlayer] | None = None
        for incoming in bench:
            for outgoing in lineup:
                gain = incoming.sim.mean - outgoing.sim.mean
                if gain < upgrade_margin:
                    continue
                candidate = [
                    p for p in lineup if p.player_id != outgoing.player_id
                ]
                candidate.append(incoming)
                if not is_legal_lineup(candidate, slots):
                    continue
                if best_swap is None or gain > best_swap[0]:
                    best_swap = (gain, incoming, outgoing)
        if best_swap is None:
            return lineup
        gain, incoming, outgoing = best_swap
        lineup = [p for p in lineup if p.player_id != outgoing.player_id]
        lineup.append(incoming)
        notes.append(
            f"Obvious upgrade: started {incoming.name} over {outgoing.name} "
            f"(+{gain:.1f} projected)."
        )


def _canonical(players: Sequence[RosterPlayer]) -> tuple[RosterPlayer, ...]:
    return tuple(sorted(players, key=lambda p: p.player_id))


def build_opponent_lineup(
    roster: Sequence[RosterPlayer],
    *,
    yahoo_starters: Sequence[str] | None = None,
    prior_week_starters: Sequence[str] | None = None,
    slots: LineupSlots = RIP_TIDE_SLOTS,
    upgrade_margin: float = DEFAULT_UPGRADE_MARGIN,
) -> OpponentLineup:
    """Assemble the opponent's likely lineup and say which assumption was used.

    ``roster`` is the opponent's full non-IR roster (starters and bench).
    ``yahoo_starters`` / ``prior_week_starters`` are ``player_id`` sequences from
    the assisted pull and the prior weekly snapshot; either may be ``None``.
    """
    by_id = {player.player_id: player for player in roster}
    notes: list[str] = []

    # 1. Yahoo-set lineup, if it is complete, legal, and all healthy.
    if yahoo_starters is not None:
        picked = [by_id[s] for s in yahoo_starters if s in by_id]
        if (
            len(picked) == len(yahoo_starters) == slots.size
            and all(p.available for p in picked)
            and is_legal_lineup(picked, slots)
        ):
            return OpponentLineup(
                players=_canonical(picked),
                assumption="yahoo-set",
                notes=("Opponent's Yahoo-set lineup was complete, legal, and healthy.",),
            )
        notes.append(
            "Yahoo-set lineup was present but incomplete, illegal, or had an "
            "unavailable starter; fell back to a heuristic."
        )

    # 2. Prior-week starters, adjusted for availability and obvious upgrades.
    if prior_week_starters is not None:
        kept: list[RosterPlayer] = []
        for player_id in prior_week_starters:
            player = by_id.get(player_id)
            if player is None:
                notes.append(
                    f"Prior-week starter {player_id} is no longer on the roster."
                )
                continue
            if not player.available:
                notes.append(f"Dropped {player.name}: unavailable (injury or bye).")
                continue
            kept.append(player)

        bench = [
            p
            for p in roster
            if p.available and all(k.player_id != p.player_id for k in kept)
        ]
        filled = _fill_to_legal(kept, bench, slots, notes)
        if filled is not None:
            upgraded = _apply_obvious_upgrades(
                filled, roster, slots, upgrade_margin, notes
            )
            return OpponentLineup(
                players=_canonical(upgraded),
                assumption="prior-week-heuristic",
                notes=tuple(notes),
            )
        notes.append(
            "Prior-week lineup could not be completed into a legal lineup; "
            "fell back to the projection heuristic."
        )

    # 3. Nothing to lean on: assume the highest-projected legal lineup.
    available = [p for p in roster if p.available]
    best = _best_projection_lineup(available, slots)
    if best is None:
        raise ValueError(
            "opponent roster cannot field a legal lineup from available players"
        )
    notes.append(
        "No Yahoo-set or prior-week lineup available; assumed the opponent "
        "starts their highest-projected legal lineup from available players. "
        "This is a fallback, not an assumption that they play optimally."
    )
    return OpponentLineup(
        players=_canonical(best),
        assumption="projection-heuristic",
        notes=tuple(notes),
    )
