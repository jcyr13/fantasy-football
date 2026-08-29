from __future__ import annotations

from datetime import date

from deadparrots.trade import trade_desk
from trade_fixtures import a_state, flat, player, ramp, rival, spot

# issue #13 acceptance criterion 6: fed a hand-built fixture league state,
# rankings and threshold filtering assert correctly. This exercises the whole
# layer end to end over one assembled state.


def _hand_built_state():
    # --- players -------------------------------------------------------
    buy_low = player(
        "amari-rising",
        "WR",
        points=flat(7.5, 6),  # output flat
        snap=ramp(0.35, 0.05, 6),  # usage climbing hard
        target=ramp(0.10, 0.03, 6),
        route=ramp(0.45, 0.05, 6),
        red_zone=ramp(0.03, 0.02, 6),
        market_rank=34,  # market: fringe WR3
        model_points=250.0,
    )
    sell_high = player(
        "deebo-spiking",
        "WR",
        points=ramp(6.0, 3.5, 6),  # output spiking
        snap=flat(0.58, 6),  # usage flat
        target=flat(0.19, 6),
        route=flat(0.64, 6),
        red_zone=flat(0.08, 6),
        market_rank=7,  # market: solid WR1/2
        model_points=140.0,
        on_dead_parrots=True,
        injury_risk=0.4,
    )
    borderline_sell = player(
        "jaylen-warm",
        "WR",
        points=ramp(8.0, 2.0, 6),
        snap=flat(0.50, 6),
        target=flat(0.16, 6),
        route=flat(0.55, 6),
        red_zone=flat(0.07, 6),
        market_rank=18,
        model_points=175.0,  # model WR ~ mid; edge just under a tier, no risk
        on_dead_parrots=True,
    )
    steady = player(
        "steady-eddie",
        "WR",
        points=flat(12.0, 6),
        snap=flat(0.7, 6),
        target=flat(0.24, 6),
        route=flat(0.8, 6),
        red_zone=flat(0.12, 6),
        market_rank=15,
        model_points=210.0,
        on_dead_parrots=True,
    )
    # filler so WR positional ranks are well-defined (a realistic ~24-deep pool)
    fillers = [
        player(f"wr-fill-{i}", "WR", points=flat(6.0, 4), model_points=260.0 + i)
        for i in range(20)
    ]

    # --- rivals ------------------------------------------------------
    tank = rival(
        "tank-commander",
        name="Tank Commander",
        wins=1,
        losses=7,
        points_for=[78.0, 82.0, 75.0, 80.0, 79.0, 77.0, 83.0, 76.0],
        roster=[spot(f"tc-{i}", "RB", age_years=31, bye_week=11) for i in range(6)],
    )
    slipping = rival(
        "slipping",
        name="Slipping",
        wins=3,
        losses=5,
        points_for=[95.0, 99.0, 92.0, 97.0, 94.0, 96.0, 91.0, 98.0],
        roster=[spot(f"sl-{i}", "RB", age_years=29, bye_week=10) for i in range(6)],
    )
    middling = rival(
        "middling",
        name="Middling",
        wins=4,
        losses=4,
        points_for=[110.0, 112.0, 108.0, 111.0, 109.0, 113.0, 107.0, 110.0],
        roster=[spot(f"md-{i}", "RB", age_years=26, bye_week=3) for i in range(6)],
    )
    contender = rival(
        "contender",
        name="Contender",
        wins=7,
        losses=1,
        points_for=[135.0, 138.0, 132.0, 140.0, 134.0, 139.0, 131.0, 137.0],
        roster=[spot(f"ct-{i}", "RB", age_years=24, bye_week=3) for i in range(6)],
    )

    return a_state(
        players=[buy_low, sell_high, borderline_sell, steady, *fillers],
        rivals=[middling, tank, contender, slipping],
        current_week=9,
        as_of_date=date(2026, 10, 27),
        dead_parrots_points_for=[120.0, 125.0, 118.0, 130.0],
    )


def test_trade_desk_reports_opportunity_for_every_player():
    state = _hand_built_state()
    desk = trade_desk(state)
    assert {o.player_id for o in desk.opportunity} == {p.player_id for p in state.players}
    assert desk.season == state.season and desk.week == state.current_week


def test_buy_low_and_sell_high_are_classified_and_thresholded():
    desk = trade_desk(_hand_built_state())

    assert [c.player_id for c in desk.buy_low] == ["amari-rising"]
    assert [c.player_id for c in desk.sell_high] == ["deebo-spiking"]

    # the flat/flat and steady players never classify
    surfaced_ids = {c.player_id for c in desk.candidates}
    assert "steady-eddie" not in surfaced_ids
    # the borderline sell-high has the right trend but its raw rank gap stays
    # under a tier -> filtered, and the weight cannot rescue it (criterion 3)
    assert "jaylen-warm" not in surfaced_ids

    deebo = desk.sell_high[0]
    assert deebo.sell_high_weight > 1.0  # injury risk 0.4 raised the weight
    assert abs(deebo.trade_edge) >= deebo.edge_tier  # surfaced on the raw gap
    assert deebo.priority == abs(deebo.trade_edge) * deebo.sell_high_weight


def test_candidates_carry_their_reasons():
    desk = trade_desk(_hand_built_state())
    for c in desk.candidates:
        assert len(c.reasons) >= 2
        assert any("tier" in r for r in c.reasons)


def test_desperate_team_ranking_and_reasons():
    desk = trade_desk(_hand_built_state())
    read = desk.desperate_teams

    assert read.ranked[0].team_id == "tank-commander"
    assert read.ranked[-1].team_id == "contender"
    assert [t.rank for t in read.ranked] == [1, 2, 3, 4]
    assert len(read.surfaced) == 3
    assert [t.team_id for t in read.surfaced] == [t.team_id for t in read.ranked[:3]]

    reasons = " ".join(read.surfaced[0].reasons).lower()
    assert "below .500" in reasons and "percentile" in reasons


def test_countdown_to_november_28():
    desk = trade_desk(_hand_built_state())
    assert desk.countdown.target_date == date(2026, 11, 28)
    assert desk.countdown.days_remaining == 32
    assert desk.countdown.is_past is False


def test_layer_is_pure_same_state_same_answer():
    a = trade_desk(_hand_built_state())
    b = trade_desk(_hand_built_state())
    assert a == b
