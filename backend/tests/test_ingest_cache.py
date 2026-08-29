from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from deadparrots.ingest.cache import (
    NflverseParquetCache,
    PullArtifactExistsError,
    register_nflverse_views,
)
from deadparrots.ingest.datasets import DATASETS_BY_NAME
from deadparrots.ingest.normalize import normalize

PULLED_AT = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _normalized(name, raw_nflverse, pull_id="20260828T120000Z"):
    spec = DATASETS_BY_NAME[name]
    fixture = "player_stats" if name == "idp" else name
    return normalize(spec, raw_nflverse(fixture), pull_id=pull_id, pulled_at=PULLED_AT)


def test_write_lands_timestamped_parquet_under_data_nflverse(tmp_path, raw_nflverse):
    cache = NflverseParquetCache(tmp_path / "data")

    path = cache.write(_normalized("pbp", raw_nflverse))

    assert path == tmp_path / "data" / "nflverse" / "20260828T120000Z" / "pbp.parquet"
    assert path.exists()


def test_write_refuses_to_overwrite_an_existing_pull_artifact(tmp_path, raw_nflverse):
    cache = NflverseParquetCache(tmp_path / "data")
    cache.write(_normalized("pbp", raw_nflverse))

    with pytest.raises(PullArtifactExistsError):
        cache.write(_normalized("pbp", raw_nflverse))


def test_pull_ids_and_latest_parquet_path_track_the_newest_pull(tmp_path, raw_nflverse):
    cache = NflverseParquetCache(tmp_path / "data")
    cache.write(_normalized("pbp", raw_nflverse, pull_id="20260101T000000Z"))
    cache.write(_normalized("pbp", raw_nflverse, pull_id="20260815T000000Z"))

    assert cache.pull_ids() == ["20260101T000000Z", "20260815T000000Z"]
    assert cache.latest_parquet_path("pbp").parent.name == "20260815T000000Z"
    assert cache.latest_parquet_path("schedules") is None


def test_cached_parquet_is_queryable_through_duckdb(tmp_path, raw_nflverse):
    cache = NflverseParquetCache(tmp_path / "data")
    pbp = _normalized("pbp", raw_nflverse)
    cache.write(pbp)

    conn = duckdb.connect()
    created = register_nflverse_views(conn, cache)

    assert "pbp" in created
    count = conn.execute("SELECT count(*) FROM nflverse_pbp").fetchone()[0]
    assert count == pbp.row_count
    cols = {row[0] for row in conn.execute("DESCRIBE nflverse_pbp").fetchall()}
    assert {"ingest_pull_id", "ingest_source"} <= cols


def test_register_views_points_at_the_latest_pull(tmp_path, raw_nflverse):
    cache = NflverseParquetCache(tmp_path / "data")
    cache.write(_normalized("schedules", raw_nflverse, pull_id="20260101T000000Z"))
    cache.write(_normalized("schedules", raw_nflverse, pull_id="20260815T000000Z"))

    conn = duckdb.connect()
    register_nflverse_views(conn, cache)

    view_sql = conn.execute(
        "SELECT sql FROM duckdb_views() WHERE view_name = 'nflverse_schedules'"
    ).fetchone()[0]
    assert "20260815T000000Z" in view_sql
