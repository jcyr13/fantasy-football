"""RIP TIDE Waiver / Free Agents layer (issue #14; methodology §4.10–§4.12).

``waiver_wire(state)`` is a pure function over an assembled weekly
:class:`WaiverState`, producing two ranked free-agent lists and nothing that
recommends a transaction:

* :func:`rest_of_season_value` — free agents ranked by **value over
  replacement**: projected points over the remaining schedule minus the best
  *other* freely-available player at the position (§4.10);
* :func:`streamer_options` — this-week streamers ranked by **next-week ceiling
  (P90)**, scoped to the roles Dead Parrots have a current bye/injury hole at
  (§4.11), K / DEF / IDP dominating in practice.

Every entry on both lists carries a :class:`BenchNeedFit` (roster construction
plus the per-role bye-crunch weeks), the player's own upcoming bye
(:class:`OwnByeNote`), and a :class:`WaiverPriorityVerdict` — whether the
rest-of-season gain is worth dropping to last in the no-FAAB
reverse-standings queue (§4.12). The current queue slot is surfaced once
(:class:`WaiverPriorityStanding`), and :func:`roster_cutdown_window` flags the
~24–48h post-roster-cutdown / practice-squad-churn waiver window.

Every tunable is in :class:`WaiverParams`. See ADR-0011.
"""

from __future__ import annotations

from .inputs import FreeAgent, RosteredPlayer, WaiverState
from .needs import BenchNeedFit, RoleDepth, bench_need_fit, bench_need_fits
from .own_bye import OwnByeNote, own_bye_note
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams, last_tuesday_of_august
from .priority import (
    WaiverPriorityStanding,
    WaiverPriorityVerdict,
    WaiverVerdict,
    priority_verdict,
    waiver_priority_standing,
)
from .replacement import (
    FreeAgentValue,
    ReplacementLevel,
    replacement_level_for,
    rest_of_season_value,
)
from .streamers import StreamerOption, streamer_options
from .window import WaiverWindowFlag, roster_cutdown_window
from .wire import WaiverWire, waiver_wire

__all__ = [
    "DEFAULT_WAIVER_PARAMS",
    "BenchNeedFit",
    "FreeAgent",
    "FreeAgentValue",
    "OwnByeNote",
    "ReplacementLevel",
    "RoleDepth",
    "RosteredPlayer",
    "StreamerOption",
    "WaiverParams",
    "WaiverPriorityStanding",
    "WaiverPriorityVerdict",
    "WaiverState",
    "WaiverVerdict",
    "WaiverWindowFlag",
    "WaiverWire",
    "bench_need_fit",
    "bench_need_fits",
    "last_tuesday_of_august",
    "own_bye_note",
    "priority_verdict",
    "replacement_level_for",
    "rest_of_season_value",
    "roster_cutdown_window",
    "streamer_options",
    "waiver_priority_standing",
    "waiver_wire",
]
