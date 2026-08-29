from __future__ import annotations

import dataclasses

from deadparrots.trade import DEFAULT_TRADE_PARAMS, desperate_team_read
from trade_fixtures import a_state, rival, spot

# methodology §4.9 / issue #13 acceptance criterion 4: the desperate-team
# ranking order and per-team reasons are produced.


def _healthy(team_id: str) -> object:
    """A contender: winning record, high points-for, young roster, no byes left."""
    return rival(
        team_id,
        wins=7,
        losses=1,
        points_for=[130.0, 135.0, 128.0, 140.0, 132.0, 138.0, 129.0, 136.0],
        roster=[spot(f"{team_id}-p{i}", "RB", age_years=24, bye_week=3) for i in range(6)],
    )


def _desperate(team_id: str) -> object:
    """Sub-.500, low points-for, old roster, several byes still ahead."""
    return rival(
        team_id,
        wins=1,
        losses=7,
        points_for=[80.0, 85.0, 78.0, 82.0, 79.0, 84.0, 77.0, 81.0],
        roster=[spot(f"{team_id}-p{i}", "RB", age_years=31, bye_week=11) for i in range(6)],
    )


def _middling(team_id: str) -> object:
    return rival(
        team_id,
        wins=4,
        losses=4,
        points_for=[110.0, 108.0, 112.0, 109.0, 111.0, 107.0, 113.0, 110.0],
        roster=[spot(f"{team_id}-p{i}", "RB", age_years=27, bye_week=3) for i in range(6)],
    )


def test_the_desperate_team_ranks_first_and_the_contender_last():
    state = a_state(
        rivals=[_middling("mid-a"), _healthy("good"), _desperate("bad"), _middling("mid-b")],
        current_week=9,
    )
    read = desperate_team_read(state)
    assert [t.team_id for t in read.ranked][0] == "bad"
    assert [t.team_id for t in read.ranked][-1] == "good"
    # scores are monotone non-increasing in rank order
    scores = [t.score for t in read.ranked]
    assert scores == sorted(scores, reverse=True)
    assert [t.rank for t in read.ranked] == [1, 2, 3, 4]


def test_surfaced_is_the_top_n_by_score():
    state = a_state(
        rivals=[_middling(f"m{i}") for i in range(5)] + [_desperate("bad"), _healthy("good")]
    )
    read = desperate_team_read(state)
    assert len(read.surfaced) == DEFAULT_TRADE_PARAMS.desperate_surface_count
    assert read.surfaced == read.ranked[:3]
    assert read.surfaced[0].team_id == "bad"


def test_surfaced_team_reasons_name_the_components_that_flagged_it():
    state = a_state(rivals=[_desperate("bad"), _healthy("good"), _middling("mid")])
    bad = desperate_team_read(state).ranked[0]
    assert bad.team_id == "bad"
    blob = " ".join(bad.reasons).lower()
    assert "below .500" in blob
    assert "percentile" in blob
    assert "years" in blob
    assert "bye" in blob
    # every reason corresponds to a component that actually cleared the threshold
    flagged = {c.name for c in bad.components if c.normalized >= 0.5}
    assert len(bad.reasons) == len(flagged)


def test_each_component_is_normalized_within_the_rival_set():
    state = a_state(rivals=[_desperate("bad"), _healthy("good"), _middling("mid")])
    read = desperate_team_read(state)
    for name in ("record", "points_for", "roster_age", "bye_crunch"):
        vals = sorted(
            next(c.normalized for c in t.components if c.name == name) for t in read.ranked
        )
        assert vals[0] == 0.0 and vals[-1] == 1.0  # min-max hits both ends


def test_a_component_with_no_spread_contributes_nothing():
    # identical rosters/records/PF except record differs -> only record has spread
    base = rival(
        "x",
        wins=4,
        losses=4,
        points_for=[100.0] * 6,
        roster=[spot("x-p", "RB", age_years=26, bye_week=2)],
    )
    a = dataclasses.replace(base, team_id="a", wins=1, losses=7)
    b = dataclasses.replace(base, team_id="b", wins=6, losses=2)
    c = dataclasses.replace(base, team_id="c", wins=4, losses=4)
    read = desperate_team_read(a_state(rivals=[a, b, c]))
    for t in read.ranked:
        for comp in t.components:
            if comp.name != "record":
                assert comp.normalized == 0.0
    assert read.ranked[0].team_id == "a"  # worst record wins on the only live signal


def _pf_raw(read, team_id: str) -> float:
    team = next(t for t in read.ranked if t.team_id == team_id)
    return next(c for c in team.components if c.name == "points_for").raw


def test_points_for_percentile_is_against_the_full_twelve_team_league():
    rivals = [_middling("m1"), _middling("m2"), _desperate("bad")]
    high_dp = desperate_team_read(
        a_state(rivals=rivals, dead_parrots_points_for=[250.0, 260.0, 255.0, 258.0])
    )
    low_dp = desperate_team_read(
        a_state(rivals=rivals, dead_parrots_points_for=[70.0, 72.0, 71.0, 73.0])
    )
    # the worst rival is below everyone either way
    assert _pf_raw(high_dp, "bad") == 1.0
    # a dominant Dead Parrots pulls the middling teams' league percentile down,
    # raising their (inverted) desperation raw
    assert _pf_raw(high_dp, "m1") > _pf_raw(low_dp, "m1")
    assert "percentile" in next(
        c for c in high_dp.ranked[0].components if c.name == "points_for"
    ).detail


def test_missing_birthdates_score_a_neutral_half_not_the_youngest_end():
    no_ages = rival(
        "no-ages",
        wins=4,
        losses=4,
        points_for=[110.0] * 6,
        roster=[spot("na-1", "DEF"), spot("na-2", "WR")],  # no birthdates
    )
    old = rival(
        "old",
        wins=4,
        losses=4,
        points_for=[110.0] * 6,
        roster=[spot("o-1", "RB", age_years=32)],
    )
    young = rival(
        "young",
        wins=4,
        losses=4,
        points_for=[110.0] * 6,
        roster=[spot("y-1", "RB", age_years=23)],
    )
    read = desperate_team_read(a_state(rivals=[no_ages, old, young]))
    age_comp = {
        t.team_id: next(c for c in t.components if c.name == "roster_age")
        for t in read.ranked
    }
    assert age_comp["no-ages"].detail == "no roster birthdates available"
    # min-max is over the teams WITH data; the no-data team lands neutral, never
    # floored to the youngest (least age-desperate) end
    assert age_comp["old"].normalized == 1.0
    assert age_comp["young"].normalized == 0.0
    assert age_comp["no-ages"].normalized == 0.5


def test_bye_crunch_counts_only_byes_still_ahead():
    team = rival(
        "t",
        wins=4,
        losses=4,
        points_for=[110.0] * 6,
        roster=[
            spot("p-past", "RB", age_years=26, bye_week=5),  # already past (week 9)
            spot("p-next", "RB", age_years=26, bye_week=10),
            spot("p-late", "RB", age_years=26, bye_week=13),
            spot("p-none", "RB", age_years=26, bye_week=None),
        ],
    )
    other = rival("o", wins=4, losses=4, points_for=[110.0] * 6, roster=[])
    read = desperate_team_read(a_state(rivals=[team, other], current_week=9))
    bye = next(c for c in read.ranked if c.team_id == "t").components
    bye_comp = next(c for c in bye if c.name == "bye_crunch")
    assert bye_comp.raw == 2.0  # weeks 10 and 13 only
