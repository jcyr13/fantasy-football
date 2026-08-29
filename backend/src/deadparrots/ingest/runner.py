from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl

from .alerts import EmailAlerter
from .cache import NflverseParquetCache, register_nflverse_views
from .datasets import NFLVERSE_DATASETS, DatasetSpec
from .normalize import normalize
from .status import PullOutcome, PullStatus, ensure_pull_status_table, record_pull_status

logger = logging.getLogger(__name__)

PULL_ID_FORMAT = "%Y%m%dT%H%M%SZ"


class NflverseSource:
    """The swappable fetch seam. Implementations return a raw nflverse payload
    for a dataset spec; the fetch itself is never unit-tested.
    """

    def load(self, spec: DatasetSpec) -> pl.DataFrame:  # pragma: no cover - protocol
        raise NotImplementedError


@dataclass(frozen=True)
class DatasetPullResult:
    dataset: str
    source: str
    status: PullOutcome
    row_count: int | None
    parquet_path: Path | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class PullRun:
    """The outcome of one nflverse pull across all requested datasets."""

    pull_id: str
    results: tuple[DatasetPullResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> list[DatasetPullResult]:
        return [r for r in self.results if not r.ok]

    def failure_alert(self) -> tuple[str, str]:
        """The (subject, body) of the email sent when a pull has failures."""
        failed = self.failures
        subject = (
            f"[Dead Parrots] nflverse pull {self.pull_id}: {len(failed)} dataset(s) failed"
        )
        lines = [
            f"nflverse pull {self.pull_id} finished with {len(failed)} failed dataset(s):",
            "",
            *(f"  - {r.dataset} ({r.source}): {r.error}" for r in failed),
            "",
            f"Succeeded: {', '.join(r.dataset for r in self.results if r.ok) or '(none)'}",
        ]
        return subject, "\n".join(lines)


def run_nflverse_pull(
    *,
    source: NflverseSource,
    cache: NflverseParquetCache,
    conn: sqlite3.Connection,
    alerter: EmailAlerter,
    datasets: Iterable[DatasetSpec] = NFLVERSE_DATASETS,
    duckdb_conn: duckdb.DuckDBPyConnection | None = None,
    pulled_at: datetime | None = None,
) -> PullRun:
    """Pull every requested nflverse dataset into the parquet cache.

    One timestamped pull set, one ``pull_status`` row per dataset. A dataset
    failure is isolated — the rest of the pull continues — and any failure at
    the end triggers a single email alert. When ``duckdb_conn`` is given, the
    ``nflverse_*`` views are refreshed after a pull that landed new data.
    """
    ensure_pull_status_table(conn)
    pulled_at = pulled_at or datetime.now(UTC)
    pull_id = pulled_at.strftime(PULL_ID_FORMAT)
    # A pull set is a directory named to the second; a benign fast re-run just
    # takes the next free second rather than colliding and looking like an outage.
    while cache.pull_dir(pull_id).exists():
        pulled_at += timedelta(seconds=1)
        pull_id = pulled_at.strftime(PULL_ID_FORMAT)

    results: list[DatasetPullResult] = []
    for spec in datasets:
        started_at = datetime.now(UTC)
        try:
            raw = source.load(spec)
            normalized = normalize(spec, raw, pull_id=pull_id, pulled_at=pulled_at)
            path = cache.write(normalized)
            result = DatasetPullResult(
                spec.name, spec.source, "ok", normalized.row_count, path, None
            )
            logger.info(
                "nflverse pull %s: %s ok (%d rows)", pull_id, spec.name, normalized.row_count
            )
        except Exception as exc:  # isolate one dataset's failure from the rest
            logger.exception("nflverse pull %s: %s failed", pull_id, spec.name)
            result = DatasetPullResult(
                spec.name, spec.source, "failed", None, None, f"{type(exc).__name__}: {exc}"
            )
        results.append(result)
        record_pull_status(
            conn,
            PullStatus(
                pull_id=pull_id,
                source=spec.source,
                dataset=spec.name,
                status=result.status,
                row_count=result.row_count,
                parquet_path=str(result.parquet_path) if result.parquet_path else None,
                error=result.error,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            ),
        )

    run = PullRun(pull_id, tuple(results))

    if duckdb_conn is not None and any(r.ok for r in results):
        try:
            register_nflverse_views(duckdb_conn, cache)
        except Exception:  # a view-refresh problem must not fail the pull itself
            logger.exception("nflverse pull %s: refreshing DuckDB views failed", pull_id)

    if not run.ok:
        alerter.send(*run.failure_alert())

    return run
