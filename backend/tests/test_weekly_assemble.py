"""``assemble_week`` over the fixture world (issue #16; ADR-0013)."""

from __future__ import annotations

from deadparrots.lineup import is_legal_lineup
from deadparrots.weekly import build_weekly_view, compute_lineup_lab
from weekly_fixtures import assemble_fixture_week


def test_assembles_both_rosters_and_resolves_players():
    week = assemble_fixture_week()

    assert week.season == 2026
    assert week.week == 3
    assert week.dead_parrots_team_name == "Dead Parrots"
    assert week.opponent_team_name == "Spanish Inquisition"
    assert len(week.dead_parrots) == 14
    assert len(week.opponent) == 14
    # Every skill player matched an nflverse identity in the rosters frame.
    unresolved = [p.name for p in week.dead_parrots if not p.resolved]
    assert unresolved == []


def test_scored_history_feeds_the_projection():
    week = assemble_fixture_week()
    qb = next(p for p in week.dead_parrots if p.name == "Jed Signal")
    # Two completed weeks of real stat lines, scored by the validated engine.
    assert qb.projection.components.current_season_games == 2
    assert qb.projection.floor < qb.projection.projection < qb.projection.ceiling
    assert qb.projection.projection > 10


def test_caveats_name_every_approximation():
    week = assemble_fixture_week()
    joined = " ".join(week.caveats)
    assert "opportunity baseline" in joined
    assert "points-for" in joined  # league-history approximation
    assert "desperate-team" in joined


def test_weekly_view_recommends_a_legal_lineup():
    week = assemble_fixture_week()
    view = build_weekly_view(week)

    rec = view.optimizer.recommendation.lineup
    assert len(rec.players) == 10
    assert is_legal_lineup(list(rec.players))
    assert 0.0 <= view.optimizer.recommendation.p_win <= 1.0
    # gap drivers decompose the mean gap slot-by-slot
    assert len(view.optimizer.gap_drivers) == 10
    assert len(view.optimizer.swing_players) == 10


def test_opponent_uses_the_yahoo_set_lineup():
    week = assemble_fixture_week()
    view = build_weekly_view(week)
    assert view.opponent_lineup.assumption == "yahoo-set"


def test_strategic_layers_populate():
    week = assemble_fixture_week()
    view = build_weekly_view(week)

    assert view.outlook.week == 3
    assert 0.0 <= view.outlook.playoff_odds.dead_parrots_odds <= 1.0
    assert view.trade.countdown.target_date.month == 11
    assert view.waiver.waiver_priority.current_priority == 11  # from the standings pull


def test_lineup_lab_marks_an_illegal_lineup():
    week = assemble_fixture_week()
    ids = [p.player_id for p in week.dead_parrots[:10]]  # arbitrary 10, not slot-legal

    result = compute_lineup_lab(week, ids)
    assert result.reason is not None
    # a known-legal lineup: the optimizer's own recommendation
    view = build_weekly_view(week)
    legal_ids = [p.player_id for p in view.optimizer.recommendation.lineup.players]
    ok = compute_lineup_lab(week, legal_ids)
    assert ok.legal
    assert ok.floor < ok.ceiling
    assert 0.0 <= ok.win_probability <= 1.0


def test_rng_seed_is_stable_across_assemblies():
    a = assemble_fixture_week()
    b = assemble_fixture_week()
    assert a.rng_seed == b.rng_seed
    assert (
        build_weekly_view(a).optimizer.recommendation.p_win
        == build_weekly_view(b).optimizer.recommendation.p_win
    )
