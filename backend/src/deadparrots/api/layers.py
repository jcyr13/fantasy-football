from __future__ import annotations

from fastapi import APIRouter, Request

from ..strategy import team_outlook
from ..trade import trade_desk
from ..waiver import waiver_wire
from ._deps import assembled_week
from .schemas import FreeAgentsResponse, TeamOutlookResponse, TradeDeskResponse
from .serialize import (
    serialize_free_agents,
    serialize_team_outlook,
    serialize_trade_desk,
)

router = APIRouter(tags=["layers"])

# The three strategic-layer endpoints (spec issue #16). Each assembles the week
# and runs one pure layer; ``caveats`` from the assembly rides along so the UI
# can flag the v1 approximations (ADR-0013 §4, §6). Serialization is shared with
# the weekly-snapshot capture (issue #17) via ``api/serialize.py``.


@router.get("/team-outlook", response_model=TeamOutlookResponse)
def team_outlook_endpoint(request: Request) -> TeamOutlookResponse:
    """Team strength, expected vs actual wins, the contend/rebuild/hold signal
    with its inputs, and the bye-week crunch map with grades."""
    a = assembled_week(request)
    return serialize_team_outlook(
        team_outlook(a.league_state, playoff_sim_seed=a.rng_seed), a.caveats
    )


@router.get("/trade-desk", response_model=TradeDeskResponse)
def trade_desk_endpoint(request: Request) -> TradeDeskResponse:
    """Per-player opportunity scores, buy-low/sell-high candidates with the
    market-value proxy and trade edge, the desperate-team read with reasons, and
    the November-28 countdown."""
    a = assembled_week(request)
    return serialize_trade_desk(trade_desk(a.trade_state), a.caveats)


@router.get("/free-agents", response_model=FreeAgentsResponse)
def free_agents_endpoint(request: Request) -> FreeAgentsResponse:
    """The two ranked free-agent lists with bench-need fit, own byes, and the
    worth-the-priority verdict, plus the current waiver priority and the
    post-cutdown window flag."""
    a = assembled_week(request)
    return serialize_free_agents(waiver_wire(a.waiver_state), a.caveats)
