from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deadparrots.config import Settings
from deadparrots.consensus.normalize import normalize
from deadparrots.consensus.raw import RawConsensusPayload
from deadparrots.consensus.sources import (
    ConsensusSourceError,
    FallbackConsensusSource,
    NoFreshConsensusDrop,
    RSidecarConsensusSource,
    SleeperConsensusSource,
    build_consensus_source,
    build_sleeper_payload,
)
from deadparrots.scoring import ScoringUnit

CONSENSUS_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "consensus"
FIXED_NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)


# --- Sleeper stopgap: raw API response -> payload -> scored feed -----------


def test_build_sleeper_payload_merges_projections_with_player_metadata():
    raw = json.loads((CONSENSUS_FIXTURE_DIR / "sleeper_projections_raw.json").read_text())

    payload = build_sleeper_payload(
        raw["projections"],
        raw["players_index"],
        season=2026,
        week=1,
        generated_at=FIXED_NOW,
    )

    assert payload["source"] == "sleeper"
    assert payload["season"] == 2026 and payload["week"] == 1
    names = [p["name"] for p in payload["players"]]
    assert names == ["Jalen Hurts", "Dallas Cowboys"]  # the empty-stats row is dropped
    hurts = payload["players"][0]
    assert hurts["sleeper_id"] == "6904"
    assert hurts["position"] == "QB"
    assert hurts["source_points"] == 22.0

    # and it flows straight through the normalizer to a scored feed
    feed = normalize(_wrap(payload, season=2026, week=1))
    assert feed.get("Jalen Hurts").projection == pytest.approx(24.8)
    assert feed.get("Dallas Cowboys").unit is ScoringUnit.TEAM_DEFENSE


def _wrap(payload: dict, *, season: int, week: int):
    return RawConsensusPayload(
        source="sleeper",
        season=season,
        week=week,
        fetched_at=FIXED_NOW,
        url="test://sleeper",
        body=json.dumps(payload),
    )


# --- rsidecar drop reader ------------------------------------------------------


def _write_drop(dir_, name, *, week=1, players=None):
    dir_.mkdir(parents=True, exist_ok=True)
    body = {"payload_version": 1, "season": 2026, "week": week, "players": players or []}
    path = dir_ / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_rsidecar_source_serves_the_newest_drop_for_the_week(tmp_path):
    incoming = tmp_path / "consensus" / "rsidecar"
    _write_drop(incoming, "20260902T110000Z.json")
    newest = _write_drop(incoming, "20260909T110000Z.json", players=[{"x": 1}])

    payload = RSidecarConsensusSource(incoming).fetch(2026, 1)

    assert payload.source == "ffanalytics"
    assert json.loads(payload.body) == json.loads(newest.read_text())


def test_rsidecar_source_rejects_a_drop_for_the_wrong_week(tmp_path):
    incoming = tmp_path / "in"
    _write_drop(incoming, "20260909T110000Z.json", week=2)

    with pytest.raises(NoFreshConsensusDrop, match="week 2"):
        RSidecarConsensusSource(incoming).fetch(2026, 1)


def test_rsidecar_source_rejects_a_stale_drop(tmp_path):
    incoming = tmp_path / "in"
    drop = _write_drop(incoming, "20260801T110000Z.json")
    import os

    old = (FIXED_NOW - timedelta(days=30)).timestamp()
    os.utime(drop, (old, old))

    with pytest.raises(NoFreshConsensusDrop, match="older than"):
        RSidecarConsensusSource(incoming, clock=lambda: FIXED_NOW).fetch(2026, 1)


def test_rsidecar_source_raises_when_no_drop_exists(tmp_path):
    with pytest.raises(NoFreshConsensusDrop, match="has the rsidecar run"):
        RSidecarConsensusSource(tmp_path / "empty", clock=lambda: FIXED_NOW).fetch(2026, 1)


# --- fallback + factory ------------------------------------------------------


class _Boom:
    source_label = "boom"

    def fetch(self, season, week):
        raise RuntimeError("down")


class _Ok:
    source_label = "ok"

    def __init__(self, payload):
        self._payload = payload

    def fetch(self, season, week):
        return self._payload


def test_fallback_tries_sources_in_order_and_returns_the_first_success(consensus_payload):
    good = _Ok(consensus_payload("sleeper_week1"))
    source = FallbackConsensusSource([_Boom(), good])

    assert source.fetch(2026, 1) is good._payload


def test_fallback_raises_with_every_reason_when_all_sources_fail():
    source = FallbackConsensusSource([_Boom(), _Boom()])

    with pytest.raises(ConsensusSourceError) as excinfo:
        source.fetch(2026, 1)
    assert str(excinfo.value).count("boom") == 2


def test_build_consensus_source_honours_the_setting(tmp_path):
    base = Settings(data_dir=tmp_path)

    assert isinstance(
        build_consensus_source(base.model_copy(update={"consensus_source": "sleeper"})),
        SleeperConsensusSource,
    )
    assert isinstance(
        build_consensus_source(base.model_copy(update={"consensus_source": "rsidecar"})),
        RSidecarConsensusSource,
    )
    assert isinstance(
        build_consensus_source(base.model_copy(update={"consensus_source": "auto"})),
        FallbackConsensusSource,
    )
