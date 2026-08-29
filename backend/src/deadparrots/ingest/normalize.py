from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl

from .datasets import DatasetSpec

# Provenance columns stamped onto every normalized frame so a cached parquet is
# self-describing: which pull produced it, from which source, and when.
PULL_ID_COLUMN = "ingest_pull_id"
SOURCE_COLUMN = "ingest_source"
PULLED_AT_COLUMN = "ingest_pulled_at"

_INTEGER_COLUMNS = ("season", "week")


class NormalizationError(ValueError):
    """A raw nflverse payload is missing columns the model depends on."""

    def __init__(self, dataset: str, missing_columns: list[str]) -> None:
        self.dataset = dataset
        self.missing_columns = missing_columns
        super().__init__(
            f"{dataset}: raw payload is missing required column(s): "
            f"{', '.join(missing_columns)}"
        )


@dataclass(frozen=True)
class NormalizedDataset:
    """A validated, provenance-stamped nflverse payload ready for the cache."""

    dataset: str
    source: str
    pull_id: str
    pulled_at: datetime
    frame: pl.DataFrame

    @property
    def row_count(self) -> int:
        return self.frame.height

    @property
    def columns(self) -> list[str]:
        return self.frame.columns


def normalize(
    spec: DatasetSpec,
    raw: pl.DataFrame,
    *,
    pull_id: str,
    pulled_at: datetime,
) -> NormalizedDataset:
    """Turn a raw nflverse payload into a ``NormalizedDataset``.

    Validates that the spec's key columns are present, coerces ``season`` /
    ``week`` to integers, applies the spec's column projection (used for the
    IDP carve-out), and stamps the provenance columns. Pure: ``raw`` is left
    untouched.
    """
    missing = [col for col in spec.key_columns if col not in raw.columns]
    if missing:
        raise NormalizationError(spec.name, missing)

    frame = raw
    if spec.projection_prefixes is not None:
        keep = [
            col
            for col in frame.columns
            if col in spec.key_columns or col.startswith(spec.projection_prefixes)
        ]
        frame = frame.select(keep)

    casts = [
        pl.col(col).cast(pl.Int64, strict=False)
        for col in _INTEGER_COLUMNS
        if col in frame.columns
    ]
    if casts:
        frame = frame.with_columns(casts)

    frame = frame.with_columns(
        pl.lit(pull_id).alias(PULL_ID_COLUMN),
        pl.lit(spec.source).alias(SOURCE_COLUMN),
        pl.lit(pulled_at).alias(PULLED_AT_COLUMN),
    )

    return NormalizedDataset(
        dataset=spec.name,
        source=spec.source,
        pull_id=pull_id,
        pulled_at=pulled_at,
        frame=frame,
    )
