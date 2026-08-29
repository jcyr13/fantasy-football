from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations_with_replacement, product
from typing import Protocol

from ..simulation import role_of

# RIP TIDE lineup slot rules and the legality primitives the optimizer (issue
# #11) is built on. ``docs/methodology.md`` §1 puts "lineup legality /
# enumeration" here rather than in the projection model, and CONTEXT.md ("The
# tool models this league and no other") lets the default be RIP-TIDE-specific.
#
# A *role* is the canonical position bucket the simulation already uses —
# ``QB`` / ``RB`` / ``WR`` / ``TE`` / ``K`` / ``DEF`` (team defense) / ``IDP``
# (the "D" slot). :func:`deadparrots.simulation.role_of` resolves the nflverse
# and Yahoo spellings onto it; this module never re-implements that map.

__all__ = [
    "RIP_TIDE_SLOTS",
    "HasPosition",
    "LineupSlots",
    "SlotRule",
    "assign_slots",
    "can_field_legal_lineup",
    "is_legal_lineup",
    "role_of",
]


class HasPosition(Protocol):
    """Anything the legality primitives can slot — a ``RosterPlayer`` or a
    ``SimPlayer``; both carry a ``position`` string that :func:`role_of` maps to
    a canonical role."""

    @property
    def position(self) -> str: ...


@dataclass(frozen=True)
class SlotRule:
    """One kind of starting slot: its display name, the roles eligible for it,
    and how many of it the lineup starts.

    A *fixed* slot admits exactly one role (``QB``, ``RB``, …); a *flex* slot
    admits several (RIP TIDE's ``W/R/T`` admits ``WR`` / ``RB`` / ``TE``).
    """

    name: str
    eligible_roles: frozenset[str]
    count: int

    @property
    def is_flex(self) -> bool:
        return len(self.eligible_roles) > 1


@dataclass(frozen=True)
class LineupSlots:
    """The full set of starting slots for a league.

    ``rules`` is ordered for display (QB first, the D slot last). Everything the
    enumerator and the legality check need is derived from it.
    """

    rules: tuple[SlotRule, ...]

    @property
    def size(self) -> int:
        """Total starters a legal lineup fields."""
        return sum(rule.count for rule in self.rules)

    def expanded(self) -> tuple[tuple[str, frozenset[str]], ...]:
        """One ``(slot name, eligible roles)`` entry per individual slot — the
        two ``RB`` slots appear twice — in display order."""
        out: list[tuple[str, frozenset[str]]] = []
        for rule in self.rules:
            out.extend((rule.name, rule.eligible_roles) for _ in range(rule.count))
        return tuple(out)

    def role_count_distributions(self) -> tuple[dict[str, int], ...]:
        """Every way the slots can be filled *by role count*.

        Fixed slots contribute a fixed count to their one role. Each flex slot
        adds its ``count`` across its eligible roles in every combination
        (``combinations_with_replacement``). The Cartesian product over the flex
        slots, folded onto the fixed base, is the complete set of legal
        role-count vectors — RIP TIDE's single ``W/R/T`` yields exactly three
        (an extra RB, an extra WR, or an extra TE). De-duplicated, so two flex
        slots that resolve to the same vector collapse.
        """
        base: dict[str, int] = {}
        flex_options: list[tuple[tuple[str, ...], ...]] = []
        for rule in self.rules:
            if rule.is_flex:
                roles = tuple(sorted(rule.eligible_roles))
                flex_options.append(
                    tuple(combinations_with_replacement(roles, rule.count))
                )
            else:
                (only_role,) = rule.eligible_roles
                base[only_role] = base.get(only_role, 0) + rule.count

        seen: set[frozenset[tuple[str, int]]] = set()
        distributions: list[dict[str, int]] = []
        for picks in product(*flex_options):
            counts = dict(base)
            for group in picks:
                for role in group:
                    counts[role] = counts.get(role, 0) + 1
            key = frozenset(counts.items())
            if key not in seen:
                seen.add(key)
                distributions.append(counts)
        return tuple(distributions)


RIP_TIDE_SLOTS = LineupSlots(
    (
        SlotRule("QB", frozenset({"QB"}), 1),
        SlotRule("RB", frozenset({"RB"}), 2),
        SlotRule("WR", frozenset({"WR"}), 2),
        SlotRule("TE", frozenset({"TE"}), 1),
        SlotRule("W/R/T", frozenset({"WR", "RB", "TE"}), 1),
        SlotRule("K", frozenset({"K"}), 1),
        SlotRule("DEF", frozenset({"DEF"}), 1),
        SlotRule("D", frozenset({"IDP"}), 1),
    )
)
"""RIP TIDE's ten starting slots: QB, 2×RB, 2×WR, TE, W/R/T flex, K, DEF, D."""


def assign_slots[T: HasPosition](
    players: Sequence[T],
    slots: LineupSlots = RIP_TIDE_SLOTS,
) -> tuple[tuple[str, T], ...] | None:
    """Match ``players`` onto ``slots`` one-to-one, or return ``None`` if no such
    assignment exists.

    A maximum-bipartite-matching (Kuhn's algorithm) between the individual slots
    and the players eligible for them. Because a legal lineup fills every slot
    with a distinct player, a perfect matching exists iff ``players`` is a legal
    lineup for ``slots``; :func:`is_legal_lineup` is the boolean face of this.
    The returned pairs are in slot display order; which of two same-name slots a
    player lands in is matching-dependent and not meaningful (callers that need
    a stable within-slot order sort by projection).
    """
    instances = slots.expanded()
    if len(players) != len(instances):
        return None

    roles = [role_of(p.position) for p in players]
    eligible: list[list[int]] = [
        [pi for pi, role in enumerate(roles) if role in slot_roles]
        for _, slot_roles in instances
    ]

    slot_of_player = [-1] * len(players)  # player index -> slot instance index
    player_of_slot = [-1] * len(instances)

    def _augment(slot_idx: int, seen: list[bool]) -> bool:
        for pi in eligible[slot_idx]:
            if seen[pi]:
                continue
            seen[pi] = True
            if slot_of_player[pi] == -1 or _augment(slot_of_player[pi], seen):
                slot_of_player[pi] = slot_idx
                player_of_slot[slot_idx] = pi
                return True
        return False

    for slot_idx in range(len(instances)):
        if not _augment(slot_idx, [False] * len(players)):
            return None

    return tuple(
        (instances[slot_idx][0], players[player_of_slot[slot_idx]])
        for slot_idx in range(len(instances))
    )


def is_legal_lineup(
    players: Sequence[HasPosition],
    slots: LineupSlots = RIP_TIDE_SLOTS,
) -> bool:
    """True iff ``players`` can fill every slot in ``slots`` one-to-one."""
    return assign_slots(players, slots) is not None


def can_field_legal_lineup(
    players: Sequence[HasPosition],
    slots: LineupSlots = RIP_TIDE_SLOTS,
) -> bool:
    """True iff *some* ``slots.size`` subset of ``players`` is a legal lineup.

    Unlike :func:`is_legal_lineup` (which needs exactly ``slots.size`` players),
    this asks whether a legal lineup can be *selected* from a larger pool — the
    question the bye-week crunch map asks each upcoming week once players on bye
    and unavailable players are removed (methodology §4.4, "any week a legal
    healthy lineup cannot be fielded").

    Each :meth:`LineupSlots.role_count_distributions` entry is a concrete
    per-role requirement summing to ``slots.size`` that already accounts for the
    flex. A player has exactly one role, so a distribution is fillable iff the
    pool holds at least its required count in every role; the pool can field a
    lineup iff any distribution is fillable.
    """
    counts: dict[str, int] = {}
    for player in players:
        role = role_of(player.position)
        counts[role] = counts.get(role, 0) + 1
    return any(
        all(counts.get(role, 0) >= needed for role, needed in distribution.items())
        for distribution in slots.role_count_distributions()
    )
