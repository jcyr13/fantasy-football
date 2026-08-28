from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via ``DEADPARROTS_*`` env vars."""

    model_config = SettingsConfigDict(
        env_prefix="DEADPARROTS_", env_file=".env", extra="ignore"
    )

    # Root of the data directory: parquet cache, the SQLite app DB, weekly
    # snapshots. Gitignored. Defaults to ``./data`` for local runs; the
    # container sets it to ``/data``.
    data_dir: Path = Path("data")

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "analytics.duckdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
