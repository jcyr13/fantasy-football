from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb

from .datasets import NFLVERSE_DATASETS, DatasetSpec
from .normalize import NormalizedDataset


class PullArtifactExistsError(FileExistsError):
    """Refused to overwrite an existing timestamped parquet."""


class NflverseParquetCache:
    """The append-only parquet archive of raw nflverse pulls.

    Layout: ``<root>/nflverse/<pull_id>/<dataset>.parquet``. Each pull writes a
    new timestamped set; nothing is ever overwritten. DuckDB reads the parquet
    directly, so the cache is queryable without a load step.
    """

    def __init__(self, root: Path) -> None:
        # ``root`` is the app data dir; pulls live under ``root/nflverse``.
        self._root = Path(root) / "nflverse"

    @property
    def root(self) -> Path:
        return self._root

    def pull_dir(self, pull_id: str) -> Path:
        return self._root / pull_id

    def parquet_path(self, pull_id: str, dataset: str) -> Path:
        return self.pull_dir(pull_id) / f"{dataset}.parquet"

    def write(self, dataset: NormalizedDataset) -> Path:
        """Persist a normalized dataset; raise rather than clobber an existing file."""
        path = self.parquet_path(dataset.pull_id, dataset.dataset)
        if path.exists():
            raise PullArtifactExistsError(f"refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        dataset.frame.write_parquet(path)
        return path

    def pull_ids(self) -> list[str]:
        """Every pull id present, oldest first (ids sort chronologically)."""
        if not self._root.exists():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir())

    def latest_parquet_path(self, dataset: str) -> Path | None:
        for pull_id in reversed(self.pull_ids()):
            path = self.parquet_path(pull_id, dataset)
            if path.exists():
                return path
        return None


def register_nflverse_views(
    conn: duckdb.DuckDBPyConnection,
    cache: NflverseParquetCache,
    datasets: Iterable[DatasetSpec] = NFLVERSE_DATASETS,
) -> list[str]:
    """(Re)create one ``nflverse_<dataset>`` DuckDB view per dataset that has a
    cached pull, each pointed at that dataset's most recent parquet. Returns the
    dataset names a view was created for.
    """
    created: list[str] = []
    for spec in datasets:
        path = cache.latest_parquet_path(spec.name)
        if path is None:
            continue
        literal = path.resolve().as_posix().replace("'", "''")
        conn.execute(
            f'CREATE OR REPLACE VIEW "nflverse_{spec.name}" AS '
            f"SELECT * FROM read_parquet('{literal}')"
        )
        created.append(spec.name)
    return created
