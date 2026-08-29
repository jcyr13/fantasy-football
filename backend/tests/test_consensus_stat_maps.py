from __future__ import annotations

import json
from pathlib import Path

import pytest

from deadparrots.consensus.normalize import SOURCE_STAT_MAPS
from deadparrots.scoring.rows import STATS_BY_UNIT

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "consensus"
RUN_R = Path(__file__).parents[2] / "rsidecar" / "run.R"

# Keys a source really carries that RIP TIDE does not score, so they are expected
# to be absent from the stat maps (PPR receptions, prop points).
_INTENTIONALLY_UNSCORED = {"rec", "pts_std", "pts_ppr", "pts_half_ppr"}


def test_every_stat_map_target_is_a_real_engine_stat_key():
    engine_keys = set().union(*STATS_BY_UNIT.values())
    for source, stat_map in SOURCE_STAT_MAPS.items():
        unknown = sorted(set(stat_map.values()) - engine_keys)
        assert not unknown, f"{source} map targets non-engine keys: {unknown}"


@pytest.mark.parametrize(
    ("fixture", "source"),
    [("ffanalytics_week1", "ffanalytics"), ("sleeper_week1", "sleeper")],
)
def test_fixture_stat_keys_are_covered_by_the_map(fixture, source):
    """The recorded fixture is the only tripwire for source-key drift (the R
    toolchain is never in CI — docs/adr/0005). Every stat key it carries must be
    one the map translates, or an explicitly unscored key.
    """
    data = json.loads((FIXTURE_DIR / f"{fixture}.json").read_text())
    known = set(SOURCE_STAT_MAPS[source]) | _INTENTIONALLY_UNSCORED
    seen: set[str] = set()
    for player in data["players"]:
        seen |= set(player.get("stats", {}))
    orphan = sorted(seen - known)
    assert not orphan, f"{fixture} uses stat keys the {source} map ignores: {orphan}"


def test_run_r_emits_exactly_the_ffanalytics_map_keys():
    """rsidecar/run.R's STAT_COLS right-hand values are the contract with
    _FFANALYTICS_STAT_MAP's left-hand keys — keep them in lockstep.
    """
    text = RUN_R.read_text()
    block = text.split("STAT_COLS <- c(", 1)[1].split(")", 1)[0]
    emitted = {
        part.split("=", 1)[1].strip().strip('"')
        for part in block.replace("\n", " ").split(",")
        if "=" in part
    }
    assert emitted == set(SOURCE_STAT_MAPS["ffanalytics"])
