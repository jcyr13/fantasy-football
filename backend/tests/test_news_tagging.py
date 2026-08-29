from __future__ import annotations

from deadparrots.news.models import NewsBucket
from deadparrots.news.tagging import NewsTargets, compile_targets, tag_text


def test_tags_players_from_each_bucket_in_precedence_then_name_order(news_targets):
    tags = tag_text(
        "Josh Allen and Tyreek Hill both cleared; Rashee Rice inactive",
        None,
        news_targets,
    )
    assert [(t.player_name, t.bucket) for t in tags] == [
        ("Josh Allen", NewsBucket.MY_ROSTER),
        ("Tyreek Hill", NewsBucket.OPPONENT),
        ("Rashee Rice", NewsBucket.FREE_AGENT),
    ]


def test_summary_text_is_searched_too(news_targets):
    tags = tag_text(
        "Wednesday practice notes",
        "Among the limited participants was Bijan Robinson (ankle).",
        news_targets,
    )
    assert [t.player_name for t in tags] == ["Bijan Robinson"]


def test_no_match_returns_empty(news_targets):
    assert tag_text("NFL announces Week 3 broadcast schedule", None, news_targets) == ()


def test_match_is_word_bounded():
    targets = NewsTargets(my_roster=("Josh Allen",))
    assert tag_text("Josh Allendale signs with the practice squad", None, targets) == ()
    assert len(tag_text("Josh Allen throws for 300", None, targets)) == 1


def test_punctuation_and_spacing_in_names_are_normalized_both_sides():
    # The apostrophe and any run of whitespace collapse to a single token
    # separator on both sides, so a feed's "Ja'Marr Chase" matches a roster
    # entry of "Ja'Marr Chase" regardless of how either side punctuates it.
    targets = NewsTargets(my_roster=("Ja'Marr Chase",))
    for headline in (
        "Ja'Marr Chase goes off",
        "Ja Marr  Chase goes off",
        "ja'marr chase goes off",
    ):
        assert len(tag_text(headline, None, targets)) == 1


def test_name_suffixes_are_ignored_on_both_sides():
    assert tag_text(
        "Odell Beckham Jr. signs with a contender",
        None,
        NewsTargets(free_agents=("Odell Beckham",)),
    )
    assert tag_text(
        "Odell Beckham catches a touchdown",
        None,
        NewsTargets(free_agents=("Odell Beckham Jr.",)),
    )


def test_accents_are_folded():
    targets = NewsTargets(opponent=("Nicolás Example",))
    assert len(tag_text("Nicolas Example returns kickoff", None, targets)) == 1


def test_a_player_on_two_lists_is_tagged_once_in_the_higher_bucket():
    targets = NewsTargets(
        my_roster=("Josh Allen",), free_agents=("Josh Allen",)
    )
    tags = tag_text("Josh Allen limited in practice", None, targets)
    assert len(tags) == 1
    assert tags[0].bucket is NewsBucket.MY_ROSTER


def test_compile_targets_can_be_reused_across_articles(news_targets):
    compiled = compile_targets(news_targets)
    assert tag_text("Bijan Robinson dominates", None, compiled)
    assert tag_text("Rashee Rice suspended", None, compiled)


def test_empty_targets_tag_nothing():
    assert tag_text("Josh Allen throws four touchdowns", None, NewsTargets.empty()) == ()
