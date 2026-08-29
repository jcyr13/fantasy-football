from __future__ import annotations

import dataclasses

import pytest

from deadparrots.projection import (
    InsufficientDataError,
    MatchupContext,
    OpportunityMetrics,
    PlayerGame,
    PlayerHistory,
    UsageSnapshot,
    project,
)

# The acceptance-criteria property checks for issue #9. Every ``project`` call
# here fixes ``rng_seed`` so the Monte-Carlo output is reproducible.

SEED = 20260909


def usage(snap: float = 0.6, tgt: float = 0.18, route: float = 0.7, rz: float = 0.15):
    return UsageSnapshot(
        snap_share=snap, target_share=tgt, route_participation=route, red_zone_share=rz
    )


def history(
    player_id: str = "p",
    position: str = "WR",
    *,
    n_games: int = 8,
    season: int = 2026,
    base_points: float = 13.0,
    with_usage: bool = True,
    is_rookie: bool = False,
    role_change: bool = False,
) -> PlayerHistory:
    games = tuple(
        PlayerGame(
            season=season,
            week=w,
            actual_points=base_points + (w % 3) * 2.0 - 1.0,
            expected_points=base_points,
            usage=usage(snap=0.5 + 0.01 * w) if with_usage else None,
        )
        for w in range(1, n_games + 1)
    )
    return PlayerHistory(
        player_id=player_id,
        position=position,
        games=games,
        is_rookie=is_rookie,
        role_change=role_change,
    )


def test_output_is_strictly_ordered_p10_lt_p50_lt_p90():
    p = project(
        history(n_games=8),
        OpportunityMetrics(expected_points=14.0),
        season=2026,
        week=10,
        rng_seed=SEED,
    )
    assert p.floor < p.projection < p.ceiling


@pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE", "K", "DEF", "IDP"])
@pytest.mark.parametrize("mean", [1.5, 6.0, 14.0, 28.0])
def test_ordering_holds_across_positions_and_means(position, mean):
    p = project(
        history(position=position, n_games=6),
        OpportunityMetrics(expected_points=mean),
        season=2026,
        week=9,
        rng_seed=SEED,
    )
    assert p.floor < p.projection < p.ceiling


@pytest.mark.parametrize(
    ("opp_allowed", "league_avg", "expected_factor"),
    [
        (40.0, 20.0, 1.20),   # brutal matchup, raw 2.0 -> clamped up-cap
        (5.0, 20.0, 0.80),    # shutout defense, raw 0.25 -> clamped down-cap
        (24.0, 20.0, 1.20),   # raw 1.2 -> exactly at the cap
        (22.0, 20.0, 1.10),   # raw 1.1 -> inside the band, untouched
    ],
)
def test_matchup_factor_never_exceeds_twenty_percent(opp_allowed, league_avg, expected_factor):
    p = project(
        history(n_games=6),
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=9,
        matchup=MatchupContext(
            opponent_points_allowed_to_position=opp_allowed,
            league_average_points_allowed_to_position=league_avg,
        ),
        rng_seed=SEED,
    )
    assert 0.80 <= p.components.matchup_factor <= 1.20
    assert p.components.matchup_factor == pytest.approx(expected_factor)


def test_absent_matchup_is_an_average_matchup():
    p = project(
        history(n_games=6),
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=9,
        rng_seed=SEED,
    )
    assert p.components.matchup_factor == 1.0


def test_low_confidence_for_fewer_than_four_current_season_games():
    p = project(
        history(n_games=2),
        OpportunityMetrics(expected_points=12.0),
        season=2026,
        week=9,
        rng_seed=SEED,
    )
    assert p.low_confidence
    assert "only-2-current-season-games" in p.reasons
    # blended shape: neither pure own nor pure prior
    assert 0.0 < p.components.shape_own_weight < 1.0
    assert p.components.shape_own_weight == pytest.approx(0.5)


def test_low_confidence_for_rookie_uses_consensus_fallback():
    p = project(
        history(player_id="rook", position="RB", n_games=0, is_rookie=True),
        None,
        season=2026,
        week=8,
        consensus_points=9.5,
        rng_seed=SEED,
    )
    assert p.low_confidence
    assert "rookie" in p.reasons
    assert "consensus-fallback" in p.reasons
    assert p.components.source == "consensus-fallback"
    assert p.components.mean_base == 9.5
    assert p.components.shape_own_weight == 0.0


def test_low_confidence_for_role_change_even_with_a_full_history():
    p = project(
        history(n_games=10, role_change=True),
        OpportunityMetrics(expected_points=14.0),
        season=2026,
        week=12,
        consensus_points=11.0,
        rng_seed=SEED,
    )
    assert p.low_confidence
    assert "role-change" in p.reasons
    assert p.components.source == "consensus-fallback"


@pytest.mark.parametrize("week", [1, 2, 3])
def test_weeks_one_to_three_are_low_confidence_regardless_of_history(week):
    p = project(
        history(n_games=17, season=2025),  # a full prior season of data
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=week,
        rng_seed=SEED,
    )
    # no 2026 games before week 3 -> also flagged for thin current-season history
    assert p.low_confidence
    assert "weeks-1-3-prior-driven" in p.reasons


def test_week_four_with_enough_current_season_games_is_full_confidence():
    games = tuple(
        PlayerGame(season=2026, week=w, actual_points=14.0 + w, expected_points=13.0,
                   usage=usage())
        for w in range(1, 4)
    )
    h = PlayerHistory(player_id="vet", position="WR", games=games)
    p = project(
        h,
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=4,
        rng_seed=SEED,
    )
    assert p.components.current_season_games == 3
    # 3 < 4 -> still low confidence at week 4
    assert p.low_confidence
    # but a 5th-week projection with 4 games clears it
    games4 = games + (
        PlayerGame(season=2026, week=4, actual_points=16.0, expected_points=13.0,
                   usage=usage()),
    )
    p2 = project(
        dataclasses.replace(h, games=games4),
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=5,
        rng_seed=SEED,
    )
    assert p2.components.current_season_games == 4
    assert not p2.low_confidence
    assert p2.reasons == ()


def test_consensus_fallback_when_no_current_season_history():
    h = history(n_games=17, season=2025)  # only last season
    p = project(
        h,
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=9,
        consensus_points=10.0,
        rng_seed=SEED,
    )
    assert p.components.source == "consensus-fallback"
    assert p.components.mean_base == 10.0
    assert "consensus-fallback" in p.reasons


def test_opportunity_fallback_when_no_history_and_no_consensus():
    p = project(
        PlayerHistory(player_id="x", position="TE", games=()),
        OpportunityMetrics(expected_points=7.0),
        season=2026,
        week=9,
        rng_seed=SEED,
    )
    assert p.components.source == "opportunity-fallback"
    assert "opportunity-fallback" in p.reasons


def test_raises_when_there_is_nothing_to_project():
    with pytest.raises(InsufficientDataError):
        project(
            PlayerHistory(player_id="ghost", position="WR", games=()),
            None,
            season=2026,
            week=9,
            rng_seed=SEED,
        )


def test_same_inputs_and_seed_produce_identical_output():
    args = dict(
        history=history(n_games=7),
        opportunity=OpportunityMetrics(expected_points=13.5),
        season=2026,
        week=10,
        consensus_points=12.0,
        matchup=MatchupContext(28.0, 24.0),
    )
    a = project(args["history"], args["opportunity"], season=args["season"],
                week=args["week"], consensus_points=args["consensus_points"],
                matchup=args["matchup"], rng_seed=99)
    b = project(args["history"], args["opportunity"], season=args["season"],
                week=args["week"], consensus_points=args["consensus_points"],
                matchup=args["matchup"], rng_seed=99)
    assert dataclasses.astuple(a) == dataclasses.astuple(b)


def test_different_seed_still_valid_but_generally_different():
    h = history(n_games=7)
    opp = OpportunityMetrics(expected_points=13.5)
    a = project(h, opp, season=2026, week=10, rng_seed=1)
    b = project(h, opp, season=2026, week=10, rng_seed=2)
    assert a.floor < a.projection < a.ceiling
    assert b.floor < b.projection < b.ceiling
    assert (a.floor, a.projection, a.ceiling) != (b.floor, b.projection, b.ceiling)


def test_rising_usage_lifts_the_mean_above_a_flat_usage_baseline():
    rising = tuple(
        PlayerGame(
            season=2026, week=w, actual_points=12.0, expected_points=12.0,
            usage=usage(snap=0.35 + 0.05 * w, tgt=0.10 + 0.02 * w,
                        route=0.45 + 0.05 * w, rz=0.05 + 0.02 * w),
        )
        for w in range(1, 7)
    )
    flat = tuple(
        PlayerGame(
            season=2026, week=w, actual_points=12.0, expected_points=12.0,
            usage=usage(snap=0.6, tgt=0.18, route=0.7, rz=0.15),
        )
        for w in range(1, 7)
    )
    opp = OpportunityMetrics(expected_points=12.0)
    p_rising = project(PlayerHistory("r", "WR", rising), opp, season=2026, week=7,
                       rng_seed=SEED)
    p_flat = project(PlayerHistory("f", "WR", flat), opp, season=2026, week=7,
                     rng_seed=SEED)
    assert p_rising.components.opportunity_trend_slope > 0.0
    assert p_flat.components.opportunity_trend_slope == pytest.approx(0.0, abs=1e-9)
    assert p_rising.components.mean_final > p_flat.components.mean_final


def test_projection_is_close_to_the_opportunity_mean_for_a_neutral_setup():
    # flat residuals, average matchup, flat usage -> P50 ~ the opportunity mean
    games = tuple(
        PlayerGame(season=2026, week=w, actual_points=15.0, expected_points=15.0,
                   usage=usage(snap=0.6, tgt=0.2, route=0.7, rz=0.15))
        for w in range(1, 9)
    )
    p = project(
        PlayerHistory("n", "RB", games),
        OpportunityMetrics(expected_points=15.0),
        season=2026,
        week=10,
        rng_seed=SEED,
    )
    assert p.components.mean_final == pytest.approx(15.0, abs=1e-9)
    assert p.projection == pytest.approx(15.0, abs=0.75)


def test_components_round_trips_the_adjustment_chain():
    p = project(
        history(n_games=6),
        OpportunityMetrics(expected_points=10.0),
        season=2026,
        week=9,
        matchup=MatchupContext(26.0, 20.0),  # raw 1.3 -> clamp 1.2
        rng_seed=SEED,
    )
    c = p.components
    assert c.matchup_factor_raw == pytest.approx(1.3)
    assert c.matchup_factor == pytest.approx(1.2)
    expected_mean = 10.0 * c.opportunity_trend_multiplier * 1.2
    assert c.mean_final == pytest.approx(expected_mean)
