from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from ..config import Settings
from ..consensus.models import ConsensusFeed
from ..weekly import AssembledWeek, assemble_week
from ..yahoo.models import FreeAgentListing, InjuryReport
from ..yahoo.normalize import (
    normalize_injuries,
    normalize_matchup,
    normalize_players,
    normalize_standings,
)
from ..yahoo.pages import ALL_PAGES, YahooPage
from ..yahoo.raw import YahooRawStore

# The request-time seam between the API and ``assemble_week`` (ADR-0013 §1). The
# default implementation reads the latest archived Yahoo payloads and the
# nflverse parquet views; tests inject a fake. Before the first assisted pull it
# raises ``WeeklyDataUnavailable`` and the weekly endpoints answer 503.

__all__ = [
    "DefaultWeeklyDataSources",
    "WeeklyDataSources",
    "WeeklyDataUnavailable",
]

_NFLVERSE_TABLES = ("player_stats", "snap_counts", "rosters", "schedules")


class WeeklyDataUnavailable(RuntimeError):
    """No usable weekly data yet — typically no Yahoo assisted pull has run."""


class WeeklyDataSources(Protocol):
    def assemble(
        self, *, season: int | None = None, week: int | None = None
    ) -> AssembledWeek: ...


class DefaultWeeklyDataSources:
    """Reads what the app already has on disk into one :class:`AssembledWeek`."""

    def __init__(self, settings: Settings, *, duckdb_conn=None) -> None:
        self._settings = settings
        self._duckdb = duckdb_conn
        self._yahoo = YahooRawStore(settings.data_dir)

    def assemble(
        self, *, season: int | None = None, week: int | None = None
    ) -> AssembledWeek:
        payloads = {}
        for page in ALL_PAGES:
            path = self._yahoo.latest_payload_path(page)
            if path is not None:
                payloads[page] = self._yahoo.load_payload(path.parent.name, page)

        if YahooPage.MATCHUP not in payloads:
            raise WeeklyDataUnavailable(
                "No Yahoo assisted pull has produced a matchup page yet."
            )

        matchup = normalize_matchup(payloads[YahooPage.MATCHUP])
        players = (
            normalize_players(payloads[YahooPage.PLAYERS])
            if YahooPage.PLAYERS in payloads
            else FreeAgentListing(players=())
        )
        injuries = (
            normalize_injuries(payloads[YahooPage.INJURIES])
            if YahooPage.INJURIES in payloads
            else InjuryReport(entries=())
        )
        if YahooPage.STANDINGS not in payloads:
            raise WeeklyDataUnavailable(
                "No Yahoo standings page yet — the strategic layers need it."
            )
        standings = normalize_standings(payloads[YahooPage.STANDINGS])

        resolved_week = week or matchup.week
        resolved_season = season or self._settings.season

        return assemble_week(
            matchup=matchup,
            free_agents=players,
            injuries=injuries,
            standings=standings,
            player_stats_rows=self._nflverse_rows("player_stats"),
            snap_rows=self._nflverse_rows("snap_counts"),
            roster_rows=self._nflverse_rows("rosters"),
            schedule_rows=self._nflverse_rows("schedules"),
            consensus=self._consensus(resolved_season, resolved_week),
            season=resolved_season,
            week=resolved_week,
            as_of_date=date.today(),
        )

    def _nflverse_rows(self, table: str) -> Sequence[dict]:
        if self._duckdb is None or table not in _NFLVERSE_TABLES:
            return []
        try:
            return self._duckdb.execute(
                f'SELECT * FROM "nflverse_{table}"'
            ).pl().to_dicts()
        except Exception:
            return []

    def _consensus(self, season: int, week: int) -> ConsensusFeed | None:
        # The consensus feed is an optional cross-check in v1; the projection
        # baseline caveat already covers its absence (ADR-0013 §3).
        return None
