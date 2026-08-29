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

    # nflverse ingestion (ticket #3). ``None`` lets nflreadpy default to the
    # current season; a list pins the seasons pulled. The cron fires the
    # unattended weekly refresh — Tuesday morning, after Monday-night stat
    # corrections settle.
    nflverse_seasons: list[int] | None = None
    nflverse_cron_day_of_week: str = "tue"
    nflverse_cron_hour: int = 8
    nflverse_cron_minute: int = 0
    nflverse_cron_timezone: str = "America/New_York"

    # Email alert for a failed nflverse pull goes to John. Until the SMTP values
    # are set the alert is logged at ERROR instead of emailed (no credentials to
    # send with); set ``DEADPARROTS_SMTP_HOST`` etc. to turn on real delivery.
    alert_email_to: str = "johncyrboston@gmail.com"
    alert_email_from: str = "deadparrots-dashboard@localhost"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "analytics.duckdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
