from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb

# Bump when the app-state schema changes. Feature tickets add their own tables;
# ticket #2 only needs the database to exist with this marker.
SCHEMA_VERSION = 1


def init_sqlite(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite app-state database.

    App state is weekly snapshots, saved scenarios, notes, source-pull status,
    and the later encrypted Yahoo token. ``check_same_thread`` is disabled
    because FastAPI runs sync endpoints on a threadpool.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
    if conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone() is None:
        conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
    return conn


def connect_duckdb(path: Path) -> duckdb.DuckDBPyConnection:
    """Open the DuckDB connection used for analytical queries over cached parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))
