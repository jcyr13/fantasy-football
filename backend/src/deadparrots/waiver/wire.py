from __future__ import annotations

from dataclasses import dataclass

from .inputs import WaiverState
from .needs import BenchNeedFit, bench_need_fits
from .params import DEFAULT_WAIVER_PARAMS, WaiverParams
from .priority import WaiverPriorityStanding, waiver_priority_standing
from .replacement import FreeAgentValue, rest_of_season_value
from .streamers import StreamerOption, streamer_options
from .window import WaiverWindowFlag, roster_cutdown_window

# The Waiver / Free Agents layer (issue #14): one pure function over an
# assembled weekly league state, producing the two ranked free-agent lists —
# rest-of-season value over replacement (§4.10) and this-week streamers by
# next-week ceiling scoped to a current hole (§4.11) — each entry annotated with
# bench-need fit, the player's own bye, and a worth-the-priority verdict
# (§4.12), plus the current waiver-priority slot and the post-cutdown
# waiver-window flag. It recommends no transaction.

__all__ = ["WaiverWire", "waiver_wire"]


@dataclass(frozen=True)
class WaiverWire:
    """Everything the Waiver / Free Agents layer reports for one snapshot."""

    season: int
    week: int
    rest_of_season: tuple[FreeAgentValue, ...]
    streamers: tuple[StreamerOption, ...]
    waiver_priority: WaiverPriorityStanding
    window: WaiverWindowFlag
    need_fits: tuple[BenchNeedFit, ...]
    hole_roles: tuple[str, ...]


def waiver_wire(
    state: WaiverState, *, params: WaiverParams = DEFAULT_WAIVER_PARAMS
) -> WaiverWire:
    """Assemble the Waiver / Free Agents layer for ``state`` (methodology
    §4.10–§4.12)."""
    fits = bench_need_fits(state, params)
    ros = rest_of_season_value(state, fits, params)
    ros_by_id = {r.player_id: r for r in ros}
    streamers = streamer_options(state, fits, params, ros_values=ros_by_id)

    return WaiverWire(
        season=state.season,
        week=state.current_week,
        rest_of_season=ros,
        streamers=streamers,
        waiver_priority=waiver_priority_standing(state, params),
        window=roster_cutdown_window(state, params),
        need_fits=tuple(fits[role] for role in sorted(fits)),
        hole_roles=tuple(sorted(state.hole_roles_resolved())),
    )
