from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # The NFL season the dashboard is modelling. Used by the assembled weekly
    # view (issue #16) when a request does not pin one; the current week comes
    # from the latest Yahoo matchup pull.
    season: int = 2026

    # nflverse ingestion (ticket #3). ``None`` lets nflreadpy default to the
    # current season; a list pins the seasons pulled. The cron fires the
    # unattended weekly refresh — Tuesday morning, after Monday-night stat
    # corrections settle.
    nflverse_seasons: list[int] | None = None
    nflverse_cron_day_of_week: str = "tue"
    nflverse_cron_hour: int = 8
    nflverse_cron_minute: int = 0
    nflverse_cron_timezone: str = "America/New_York"

    # Consensus feed sidecar (ticket #8). ``ffanalytics`` runs in the rsidecar
    # container and drops a raw stat-projection payload into
    # ``<data_dir>/consensus/rsidecar/``; the weekly APScheduler job re-scores it
    # to RIP TIDE rules through the engine. ``consensus_source`` picks the fetch
    # path: ``auto`` prefers the sidecar drop and falls back to the Sleeper
    # public API (the Week-1 stopgap); ``sleeper`` / ``rsidecar`` force one.
    # ``None`` season/week lets nflreadpy resolve the current NFL week. The cron
    # fires Wednesday morning, once mid-week projections have posted.
    consensus_source: Literal["auto", "sleeper", "rsidecar"] = "auto"
    consensus_season: int | None = None
    consensus_week: int | None = None
    consensus_cron_day_of_week: str = "wed"
    consensus_cron_hour: int = 6
    consensus_cron_minute: int = 0
    consensus_cron_timezone: str = "America/New_York"
    # Where the rsidecar container drops its payloads; defaults under data_dir.
    consensus_rsidecar_dir: Path | None = None

    # News module (ticket #15). ESPN's keyless NFL news endpoint plus the ESPN
    # NFL and Yahoo Sports NFL RSS feeds, polled at most every ~30 minutes; each
    # item is name-matched to players and cached to SQLite with ``fetched_at``.
    # A blank URL disables that feed. News is never part of a weekly snapshot.
    news_espn_api_url: str = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"
    )
    news_espn_rss_url: str = "https://www.espn.com/espn/rss/nfl/news"
    news_yahoo_rss_url: str = "https://sports.yahoo.com/nfl/rss/"
    news_poll_interval_minutes: int = 30
    news_window_hours: int = 48

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
    def consensus_rsidecar_incoming_dir(self) -> Path:
        return self.consensus_rsidecar_dir or (self.data_dir / "consensus" / "rsidecar")

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "analytics.duckdb"


@lru_cache
def get_settings() -> Settings:
    return Settings()
