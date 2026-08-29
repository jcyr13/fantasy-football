from __future__ import annotations

from deadparrots.trade import DEFAULT_TRADE_PARAMS, opportunity_score
from trade_fixtures import flat, player, ramp, usage

# methodology §4.5 — the opportunity score is a decay-weighted composite of the
# four usage signals set beside the fantasy-points trend over the same window.


def test_rising_usage_gives_a_positive_opportunity_trend():
    p = player(
        "wr-rising",
        "WR",
        points=flat(9.0, 6),
        snap=ramp(0.40, 0.05, 6),
        target=ramp(0.12, 0.03, 6),
        route=ramp(0.50, 0.05, 6),
        red_zone=ramp(0.05, 0.02, 6),
    )
    score = opportunity_score(p)
    assert score.opportunity_trend > 0.0
    assert abs(score.output_trend) < 1e-6
    assert score.games_counted == 6


def test_declining_usage_gives_a_negative_opportunity_trend():
    p = player(
        "wr-fading",
        "WR",
        points=flat(11.0, 6),
        snap=ramp(0.80, -0.05, 6),
        target=ramp(0.30, -0.03, 6),
        route=ramp(0.85, -0.05, 6),
        red_zone=ramp(0.25, -0.02, 6),
    )
    assert opportunity_score(p).opportunity_trend < 0.0


def test_output_trend_tracks_points_series():
    p = player("rb-hot", "RB", points=ramp(6.0, 2.0, 6))
    score = opportunity_score(p)
    assert score.output_trend > 1.9  # ~2.0 pts/game, decay-weighted
    assert score.output_index > 0.0


def test_usage_less_history_yields_a_zero_score():
    p = player("te-nodata", "TE", points=[8.0, 9.0, 10.0], snap=[])
    score = opportunity_score(p)
    assert score.games_counted == 0
    assert score == score.__class__(
        player_id="te-nodata",
        position="TE",
        opportunity_index=0.0,
        opportunity_trend=0.0,
        output_index=0.0,
        output_trend=0.0,
        games_counted=0,
        half_life_games=DEFAULT_TRADE_PARAMS.opportunity_decay_half_life_games,
    )


def test_only_usage_carrying_games_count_toward_the_window():
    from deadparrots.trade import PlayerWeek, TradePlayer

    p = TradePlayer(
        player_id="wr-gap",
        name="WR Gap",
        position="WR",
        history=(
            PlayerWeek(1, 5.0, usage(0.4, 0.1, 0.5, 0.1)),
            PlayerWeek(2, 30.0, None),  # big point week, no usage data — dropped
            PlayerWeek(3, 6.0, usage(0.45, 0.12, 0.55, 0.12)),
        ),
    )
    score = opportunity_score(p)
    assert score.games_counted == 2
    # the 30-point game is excluded, so the output index stays near 5–6
    assert score.output_index < 10.0


def test_index_is_a_share_between_zero_and_one():
    p = player(
        "wr-mid",
        "WR",
        points=flat(10.0, 5),
        snap=flat(0.6, 5),
        target=flat(0.2, 5),
        route=flat(0.7, 5),
        red_zone=flat(0.1, 5),
    )
    score = opportunity_score(p)
    # equal-weighted mean of the four flat shares
    assert score.opportunity_index == round((0.6 + 0.2 + 0.7 + 0.1) / 4, 6)


def test_decay_half_life_is_configurable():
    import dataclasses

    p = player("rb-x", "RB", points=ramp(4.0, 3.0, 8))
    short = dataclasses.replace(DEFAULT_TRADE_PARAMS, opportunity_decay_half_life_games=1.0)
    long = dataclasses.replace(DEFAULT_TRADE_PARAMS, opportunity_decay_half_life_games=12.0)
    # a shorter half-life leans harder on the most recent (steeper) games
    assert opportunity_score(p, short).output_index > opportunity_score(p, long).output_index
