from __future__ import annotations

import dataclasses

from deadparrots.trade import DEFAULT_TRADE_PARAMS, opportunity_score, trade_candidates
from trade_fixtures import a_state, flat, player, ramp

# methodology §4.6–§4.8 / issue #13 acceptance criteria 1–3:
#   - buy-low / sell-high classification matches the opportunity-vs-output defs
#   - injury risk / hard schedule increases sell-high weighting
#   - candidates below the minimum trade edge are filtered out


def _buy_low_player(market_rank: int, model_points: float = 180.0, **kw) -> object:
    """A rival WR with usage rising and points flat (the buy-low trend)."""
    return player(
        "wr-buy",
        "WR",
        points=flat(8.0, 6),
        snap=ramp(0.35, 0.04, 6),
        target=ramp(0.10, 0.03, 6),
        route=ramp(0.45, 0.04, 6),
        red_zone=ramp(0.04, 0.02, 6),
        market_rank=market_rank,
        model_points=model_points,
        **kw,
    )


def _sell_high_player(market_rank: int, model_points: float = 120.0, **kw) -> object:
    """A Dead Parrots WR with points spiking and usage flat (the sell-high trend)."""
    return player(
        "wr-sell",
        "WR",
        points=ramp(6.0, 3.0, 6),
        snap=flat(0.55, 6),
        target=flat(0.18, 6),
        route=flat(0.62, 6),
        red_zone=flat(0.10, 6),
        market_rank=market_rank,
        model_points=model_points,
        on_dead_parrots=True,
        **kw,
    )


def _rank_filler(role: str, n: int, base_points: float) -> list:
    """``n`` throwaway players at ``role`` so positional ranks are well-defined."""
    return [
        player(f"{role.lower()}-fill-{i}", role, points=flat(5.0, 4), model_points=base_points + i)
        for i in range(n)
    ]


# --- classification -------------------------------------------------------


def test_buy_low_is_flagged_when_opportunity_rises_and_output_lags():
    target = _buy_low_player(market_rank=20, model_points=300.0)
    state = a_state(players=[target, *_rank_filler("WR", 4, base_points=310.0)])
    cands = trade_candidates(state)
    assert [c.side for c in cands] == ["buy-low"]
    c = cands[0]
    assert c.player_id == "wr-buy"
    # model ranks it WR5 (four fillers score higher); market says WR20
    assert (c.model_rank, c.market_rank, c.trade_edge) == (5, 20, 15)
    assert c.priority >= c.edge_tier == 12
    assert c.sell_high_weight == 1.0
    assert any("Opportunity trending up" in r for r in c.reasons)
    assert any("clears the 12-place WR tier" in r for r in c.reasons)


def test_sell_high_is_flagged_when_output_spikes_and_opportunity_is_flat():
    target = _sell_high_player(market_rank=6, model_points=100.0)
    state = a_state(players=[target, *_rank_filler("WR", 20, base_points=101.0)])
    cands = trade_candidates(state)
    assert [c.side for c in cands] == ["sell-high"]
    c = cands[0]
    # 20 fillers all outscore it -> model WR21; market says WR6
    assert c.model_rank == 21 and c.market_rank == 6
    assert c.trade_edge == 6 - 21 == -15
    assert c.priority >= c.edge_tier == 12
    assert any("Points spiking" in r for r in c.reasons)


def test_a_flat_flat_player_is_not_a_candidate():
    p = player(
        "wr-meh",
        "WR",
        points=flat(10.0, 6),
        snap=flat(0.5, 6),
        target=flat(0.2, 6),
        route=flat(0.6, 6),
        red_zone=flat(0.1, 6),
        market_rank=40,
        model_points=200.0,
        on_dead_parrots=False,
    )
    assert trade_candidates(a_state(players=[p])) == ()


def test_buy_low_trend_on_a_dead_parrots_player_is_not_surfaced():
    # right trend, wrong ownership: you cannot buy-low your own player
    target = _buy_low_player(market_rank=20, model_points=300.0, on_dead_parrots=True)
    state = a_state(players=[target, *_rank_filler("WR", 4, base_points=310.0)])
    assert trade_candidates(state) == ()


def test_sell_high_trend_on_a_rival_player_is_not_surfaced():
    target = _sell_high_player(market_rank=6, model_points=100.0)
    rival_version = dataclasses.replace(target, on_dead_parrots=False)
    state = a_state(players=[rival_version, *_rank_filler("WR", 20, base_points=101.0)])
    assert trade_candidates(state) == ()


# --- trade-edge threshold (criterion 3) --------------------------------


def test_below_tier_edge_is_filtered_out():
    # model WR1, market WR12 -> edge 11, just under the 12-place WR tier
    target = _buy_low_player(market_rank=12, model_points=500.0)
    state = a_state(players=[target])
    assert trade_candidates(state) == ()


def test_at_tier_edge_is_surfaced():
    target = _buy_low_player(market_rank=13, model_points=500.0)  # edge exactly 12
    cands = trade_candidates(a_state(players=[target]))
    assert len(cands) == 1 and cands[0].trade_edge == 12


def test_edge_in_the_wrong_direction_is_filtered_out():
    # buy-low trend, but the market already ranks the player far ABOVE the model
    target = _buy_low_player(market_rank=2, model_points=100.0)
    state = a_state(players=[target, *_rank_filler("WR", 30, base_points=101.0)])
    assert trade_candidates(state) == ()


def test_qb_uses_the_shallower_six_place_tier():
    target = player(
        "qb-buy",
        "QB",
        points=flat(15.0, 6),
        snap=ramp(0.6, 0.05, 6),
        target=flat(0.0, 6),
        route=flat(0.0, 6),
        red_zone=ramp(0.1, 0.03, 6),
        market_rank=10,
        model_points=300.0,
        on_dead_parrots=False,
    )
    cands = trade_candidates(a_state(players=[target]))
    assert len(cands) == 1
    assert cands[0].edge_tier == 6 and cands[0].trade_edge == 9


# --- sell-high weighting (criterion 2) --------------------------------
# The injury / hard-schedule weight scales a sell-high candidate's ranking
# priority. It never moves the surfacing threshold — §4.8 keeps that on the raw
# rank gap: "Below that, it is noise and is hidden."


def _above_tier_sell_high(**kw):
    """model WR21, market WR5 -> directional edge 16, over the 12-place WR tier
    on the raw gap alone."""
    return _sell_high_player(market_rank=5, model_points=100.0, **kw), _rank_filler(
        "WR", 20, base_points=101.0
    )


def _borderline_sell_high(**kw):
    """model WR15, market WR5 -> directional edge 10, under the 12-place tier."""
    return _sell_high_player(market_rank=5, model_points=100.0, **kw), _rank_filler(
        "WR", 14, base_points=101.0
    )


def test_a_sub_tier_sell_high_stays_hidden_despite_injury_or_a_hard_schedule():
    plain, fillers = _borderline_sell_high()
    assert trade_candidates(a_state(players=[plain, *fillers])) == ()

    risky, fillers = _borderline_sell_high(injury_risk=1.0)
    assert trade_candidates(a_state(players=[risky, *fillers])) == ()

    tough, fillers = _borderline_sell_high(
        opponent_points_allowed=8.0, league_average_points_allowed=20.0
    )
    assert trade_candidates(a_state(players=[tough, *fillers])) == ()


def test_injury_risk_raises_the_sell_high_weight_and_priority():
    plain, fillers = _above_tier_sell_high()
    base = trade_candidates(a_state(players=[plain, *fillers]))[0]
    assert base.sell_high_weight == 1.0
    assert base.priority == 16.0  # the unweighted directional edge

    risky, fillers = _above_tier_sell_high(injury_risk=0.6)
    c = trade_candidates(a_state(players=[risky, *fillers]))[0]
    assert c.sell_high_weight == 1.3  # 1 + 0.5 * 0.6
    assert c.priority == 20.8  # 16 * 1.3 — ranking only
    assert c.trade_edge == base.trade_edge  # same raw edge; the filter is unchanged
    assert any("Injury risk 60%" in r for r in c.reasons)


def test_hard_schedule_raises_the_sell_high_weight_and_priority():
    tough, fillers = _above_tier_sell_high(
        opponent_points_allowed=17.0, league_average_points_allowed=20.0  # ratio 0.85
    )
    c = trade_candidates(a_state(players=[tough, *fillers]))[0]
    assert c.sell_high_weight == 1.5  # ratio 0.85 <= 0.9 -> full hardness -> +0.5
    assert c.priority == 24.0  # 16 * 1.5
    assert any("Hard upcoming schedule" in r for r in c.reasons)


def test_easy_schedule_leaves_the_weight_at_one():
    easy, fillers = _above_tier_sell_high(
        opponent_points_allowed=24.0, league_average_points_allowed=20.0  # ratio 1.2
    )
    assert trade_candidates(a_state(players=[easy, *fillers]))[0].sell_high_weight == 1.0


def test_buy_low_weighting_is_always_one():
    risky = _buy_low_player(market_rank=20, model_points=500.0, injury_risk=0.9)
    cands = trade_candidates(a_state(players=[risky]))
    assert cands[0].sell_high_weight == 1.0


# --- ordering ---------------------------------------------------------


def test_candidates_are_sorted_by_descending_priority():
    big = _buy_low_player(market_rank=40, model_points=500.0)  # edge 39
    small = player(
        "wr-buy2",
        "WR",
        points=flat(8.0, 6),
        snap=ramp(0.35, 0.04, 6),
        target=ramp(0.10, 0.03, 6),
        route=ramp(0.45, 0.04, 6),
        red_zone=ramp(0.04, 0.02, 6),
        market_rank=15,
        model_points=499.0,  # model WR2, market WR15 -> edge 13
        on_dead_parrots=False,
    )
    cands = trade_candidates(a_state(players=[small, big]))
    assert [c.player_id for c in cands] == ["wr-buy", "wr-buy2"]
    assert cands[0].priority > cands[1].priority


def test_passing_precomputed_opportunity_scores_matches_recomputing():
    target = _buy_low_player(market_rank=20, model_points=500.0)
    state = a_state(players=[target])
    precomputed = {target.player_id: opportunity_score(target, DEFAULT_TRADE_PARAMS)}
    assert trade_candidates(state, precomputed) == trade_candidates(state, None)
