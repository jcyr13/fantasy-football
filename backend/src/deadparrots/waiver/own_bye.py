from __future__ import annotations

from dataclasses import dataclass

from .inputs import FreeAgent, WaiverState
from .needs import BenchNeedFit

# The free agent's *own* upcoming bye (methodology §4.10–§4.11: each entry is
# annotated with "the player's own upcoming bye"). A short read of whether the
# bye is still ahead within the season horizon and — the part that matters for a
# roster decision — whether it lands on a week the target's role is already in a
# bye crunch, which would blunt the value of the add.

__all__ = ["OwnByeNote", "own_bye_note"]


@dataclass(frozen=True)
class OwnByeNote:
    """A free agent's own NFL bye, relative to the Dead Parrots season."""

    bye_week: int | None
    is_upcoming: bool
    collides_with_role_bye_crunch: bool
    note: str


def own_bye_note(
    player: FreeAgent, state: WaiverState, fit: BenchNeedFit
) -> OwnByeNote:
    """The own-bye annotation for ``player`` at ``fit.role``."""
    bye = player.bye_week
    is_upcoming = bye is not None and bye in set(state.upcoming_weeks())
    collides = is_upcoming and bye in fit.bye_crunch_weeks

    if bye is None:
        note = "No upcoming bye on record."
    elif not is_upcoming:
        note = f"Bye (Week {bye}) is already past — no roster impact left."
    elif collides:
        note = (
            f"Bye in Week {bye} lands on the {fit.role} bye crunch — the add "
            f"does not help that week."
        )
    else:
        note = f"Own bye in Week {bye}; plan a one-week cover then."

    return OwnByeNote(
        bye_week=bye,
        is_upcoming=is_upcoming,
        collides_with_role_bye_crunch=collides,
        note=note,
    )
