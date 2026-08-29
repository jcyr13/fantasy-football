from __future__ import annotations

from deadparrots.simulation import seed_from_snapshot_id

# Issue #10 acceptance criterion 2: "Seed is derived from the weekly snapshot
# ID; repeated runs are identical." (spec user story 64)


def test_seed_is_deterministic_for_a_snapshot_id():
    assert seed_from_snapshot_id("2026-W09") == seed_from_snapshot_id("2026-W09")


def test_seed_is_stable_across_this_run_as_a_literal():
    # A frozen expectation — a change to the derivation reshuffles every stored
    # snapshot's numbers, so it should be a deliberate, visible edit.
    assert seed_from_snapshot_id("2026-W09") == 11958311405417004574


def test_distinct_snapshot_ids_give_distinct_seeds():
    seeds = {
        seed_from_snapshot_id(s)
        for s in ("2026-W01", "2026-W02", "2026-W09", "2026-W17", "snapshot-42")
    }
    assert len(seeds) == 5


def test_accepts_int_and_str_ids_and_agrees_on_their_string_form():
    assert seed_from_snapshot_id(42) == seed_from_snapshot_id("42")


def test_seed_is_a_non_negative_64_bit_int():
    seed = seed_from_snapshot_id("2026-W09")
    assert isinstance(seed, int)
    assert 0 <= seed < 2**64
