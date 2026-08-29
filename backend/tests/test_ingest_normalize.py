from __future__ import annotations

import polars as pl
import pytest

from deadparrots.ingest.datasets import DATASETS_BY_NAME, NFLVERSE_DATASETS
from deadparrots.ingest.normalize import NormalizationError, normalize


@pytest.fixture
def pulled_at():
    from datetime import UTC, datetime

    return datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("spec", NFLVERSE_DATASETS, ids=lambda s: s.name)
def test_every_dataset_fixture_normalizes_and_gets_provenance(spec, raw_nflverse, pulled_at):
    raw = raw_nflverse("player_stats" if spec.name == "idp" else spec.name)

    normalized = normalize(spec, raw, pull_id="20260828T120000Z", pulled_at=pulled_at)

    assert normalized.dataset == spec.name
    assert normalized.source == spec.source
    assert normalized.pull_id == "20260828T120000Z"
    assert normalized.row_count == raw.height
    for col in ("ingest_pull_id", "ingest_source", "ingest_pulled_at"):
        assert col in normalized.columns
    assert normalized.frame["ingest_source"].unique().to_list() == [spec.source]
    assert normalized.frame["ingest_pull_id"].unique().to_list() == ["20260828T120000Z"]


def test_season_and_week_are_coerced_to_integers(raw_nflverse, pulled_at):
    spec = DATASETS_BY_NAME["pbp"]
    raw = raw_nflverse("pbp").with_columns(
        pl.col("season").cast(pl.String), pl.col("week").cast(pl.String)
    )

    normalized = normalize(spec, raw, pull_id="p", pulled_at=pulled_at)

    assert normalized.frame.schema["season"] == pl.Int64
    assert normalized.frame.schema["week"] == pl.Int64


def test_missing_key_column_raises_normalization_error(raw_nflverse, pulled_at):
    spec = DATASETS_BY_NAME["pbp"]
    raw = raw_nflverse("pbp").drop("season")

    with pytest.raises(NormalizationError) as excinfo:
        normalize(spec, raw, pull_id="p", pulled_at=pulled_at)

    assert "season" in str(excinfo.value)
    assert excinfo.value.dataset == "pbp"
    assert "season" in excinfo.value.missing_columns


def test_idp_projection_keeps_defensive_columns_and_drops_offense(raw_nflverse, pulled_at):
    spec = DATASETS_BY_NAME["idp"]
    raw = raw_nflverse("player_stats")

    normalized = normalize(spec, raw, pull_id="p", pulled_at=pulled_at)

    assert "def_tackles_solo" in normalized.columns
    assert "def_pass_defended" in normalized.columns
    assert "player_id" in normalized.columns
    assert "passing_yards" not in normalized.columns
    assert "fantasy_points_ppr" not in normalized.columns


def test_normalize_does_not_mutate_the_input_frame(raw_nflverse, pulled_at):
    spec = DATASETS_BY_NAME["schedules"]
    raw = raw_nflverse("schedules")
    before = raw.columns.copy()

    normalize(spec, raw, pull_id="p", pulled_at=pulled_at)

    assert raw.columns == before
    assert "ingest_source" not in raw.columns
