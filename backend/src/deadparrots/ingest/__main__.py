from __future__ import annotations

import logging
import sys

from ..config import get_settings
from ..db import connect_duckdb, init_sqlite
from .alerts import build_email_alerter
from .cache import NflverseParquetCache
from .runner import run_nflverse_pull


def main(argv: list[str] | None = None) -> int:
    """Run one nflverse pull now. Exit non-zero if any dataset failed."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    sqlite_conn = init_sqlite(settings.sqlite_path)
    duckdb_conn = connect_duckdb(settings.duckdb_path)
    try:
        from .source import LiveNflverseSource

        run = run_nflverse_pull(
            source=LiveNflverseSource(seasons=settings.nflverse_seasons),
            cache=NflverseParquetCache(settings.data_dir),
            conn=sqlite_conn,
            alerter=build_email_alerter(settings),
            duckdb_conn=duckdb_conn,
        )
    finally:
        duckdb_conn.close()
        sqlite_conn.close()

    print(f"nflverse pull {run.pull_id}")
    for result in run.results:
        rows = "-" if result.row_count is None else result.row_count
        print(f"  {result.status:6} {result.dataset:13} rows={rows} {result.error or ''}".rstrip())
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())
