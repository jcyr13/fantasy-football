from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations, product

from ..simulation import SimPlayer, role_of
from .slots import RIP_TIDE_SLOTS, LineupSlots

# The roster-facing vocabulary for the optimizer. A :class:`RosterPlayer` is one
# rostered player plus the marginal the simulation samples (its :class:`SimPlayer`);
# a :class:`Lineup` is a legal set of ten starters. Enumeration is over *distinct
# starting sets*, not slot permutations — putting a WR in the flex instead of a
# WR slot is the same ten players on the field and the same weekly total, so it
# is the same lineup here (see ADR-0008).

__all__ = [
    "Lineup",
    "RosterPlayer",
    "enumerate_lineups",
]


@dataclass(frozen=True)
class RosterPlayer:
    """A rostered player and the distribution the head-to-head sim samples for
    them.

    ``sim`` is the :class:`SimPlayer` marginal (mean / sigma / skew plus the NFL
    team and game ids the correlation model needs). ``available`` is ``False``
    for a player who cannot play this week — injured out, on bye — and is
    consulted only when building the *opponent's* likely lineup; a Dead Parrots
    lineup is enumerated from the whole non-IR roster (the caller drops IR before
    calling). ``position`` is the raw Yahoo/nflverse string; :attr:`role` is its
    canonical bucket.
    """

    player_id: str
    name: str
    position: str
    sim: SimPlayer
    available: bool = True

    @property
    def role(self) -> str:
        return role_of(self.position)


@dataclass(frozen=True)
class Lineup:
    """A legal set of starters, held in a canonical order (by ``player_id``) so
    two enumerations of the same ten players compare equal."""

    players: tuple[RosterPlayer, ...]

    @property
    def player_ids(self) -> frozenset[str]:
        return frozenset(p.player_id for p in self.players)

    @property
    def sims(self) -> tuple[SimPlayer, ...]:
        """The marginals in this lineup's canonical order — the order every
        head-to-head call for this lineup must use so common random numbers line
        up trial-for-trial (ADR-0007)."""
        return tuple(p.sim for p in self.players)


def enumerate_lineups(
    players: Sequence[RosterPlayer], slots: LineupSlots = RIP_TIDE_SLOTS
) -> Iterator[Lineup]:
    """Yield every legal lineup that can be built from ``players``.

    Provably complete and non-duplicating: a legal lineup is fixed by *how many*
    players it starts at each role (:meth:`LineupSlots.role_count_distributions`
    enumerates every legal role-count vector) and *which* players fill those
    counts (a ``combinations`` — not ``permutations`` — draw from each role's
    pool). Distinct role-count vectors differ in at least one role's count, and a
    player has exactly one role, so no starting set is produced twice; the
    ``seen`` guard only matters if the caller passes duplicate ``player_id``\\ s.
    Roles absent from a distribution, or short of players, prune that branch.
    """
    pool: dict[str, list[RosterPlayer]] = {}
    for player in players:
        pool.setdefault(player.role, []).append(player)
    for bucket in pool.values():
        bucket.sort(key=lambda p: p.player_id)

    seen: set[frozenset[str]] = set()
    for distribution in slots.role_count_distributions():
        wanted = {role: n for role, n in distribution.items() if n > 0}
        if any(len(pool.get(role, ())) < n for role, n in wanted.items()):
            continue
        per_role_choices = [
            list(combinations(pool[role], n)) for role, n in wanted.items()
        ]
        for selection in product(*per_role_choices):
            members = tuple(
                sorted(
                    (p for group in selection for p in group),
                    key=lambda p: p.player_id,
                )
            )
            ids = frozenset(p.player_id for p in members)
            if len(ids) != slots.size or ids in seen:
                continue
            seen.add(ids)
            yield Lineup(members)
