from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .raw import RawConsensusPayload

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# The single interface every consensus-projection fetch goes through (spec issue
# #8; docs/adr/0005). The R sidecar's ``ffanalytics`` run backs it in the steady
# state; the Sleeper public API is the Week-1 stopgap and the automatic fallback
# for any week the sidecar has not produced a fresh drop. Nothing downstream of
# a source knows which one answered — the payload's ``source`` field is
# provenance, not a branch.
#
# The fetch itself (reading the sidecar's file, calling Sleeper over HTTP) is
# never unit-tested — only the recorded-payload -> ``ConsensusFeed`` path is,
# exactly like ``LiveNflverseSource`` / ``BrowserYahooSource``.

# The R sidecar's payload format version this reader understands. Bump in
# lockstep with rsidecar/run.R and the ``_FFANALYTICS_STAT_MAP`` in normalize.
RSIDECAR_PAYLOAD_VERSION = 1

# Sleeper's read API (leagues, players) is documented at api.sleeper.app; its
# weekly projections live on the (undocumented) api.sleeper.com stats host. Both
# are best-effort — this whole fetch path is a Week-1 stopgap and is not tested.
SLEEPER_API_BASE = "https://api.sleeper.app"
SLEEPER_STATS_BASE = "https://api.sleeper.com"
# Sleeper groups defensive individuals under these position query values.
_SLEEPER_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "DB", "LB", "DL")


class ConsensusSourceError(RuntimeError):
    """No configured consensus source could produce a payload."""


class NoFreshConsensusDrop(Exception):
    """The ``rsidecar`` has no drop the current week can use (missing, wrong
    week, stale, or a payload version this reader does not understand). Not an
    error on its own — ``FallbackConsensusSource`` moves on to the next source.
    """


class ConsensusSource:
    """Return a raw consensus payload for one season + week. Implementations own
    the transport (a file the R sidecar wrote, or an HTTP call to Sleeper); they
    do not normalize or score.
    """

    source_label: str = "consensus"

    def fetch(self, season: int, week: int) -> RawConsensusPayload:
        raise NotImplementedError  # pragma: no cover - interface


class StaticConsensusSource(ConsensusSource):
    """Serve a fixed payload body. Handy for wiring a pull from a payload
    captured out of band (a sidecar drop copied in, a replayed archive) without
    going through a store first, and for tests.
    """

    source_label = "consensus-static"

    def __init__(self, body: str, *, source_label: str | None = None, clock=None) -> None:
        self._body = body
        self._clock = clock or (lambda: datetime.now(UTC))
        parsed = json.loads(body)
        self._source = source_label or str(parsed.get("source", self.source_label))

    def fetch(self, season: int, week: int) -> RawConsensusPayload:
        return RawConsensusPayload(
            source=self._source,
            season=season,
            week=week,
            fetched_at=self._clock(),
            url="static://consensus",
            body=self._body,
        )


class RSidecarConsensusSource(ConsensusSource):
    """Serve the newest projection drop the ``rsidecar`` container wrote.

    The sidecar runs ``ffanalytics`` on a schedule and drops one
    ``<UTC-timestamp>.json`` per run into ``incoming_dir`` (a shared volume).
    This reader picks the freshest one, checks it is for the requested week and
    not older than ``max_age``, and hands its bytes on untouched.
    """

    source_label = "ffanalytics"

    def __init__(
        self,
        incoming_dir: Path,
        *,
        max_age: timedelta = timedelta(days=8),
        clock=None,
    ) -> None:
        self._dir = Path(incoming_dir)
        self._max_age = max_age
        self._clock = clock or (lambda: datetime.now(UTC))

    def fetch(self, season: int, week: int) -> RawConsensusPayload:
        drop = self._newest_drop()
        if drop is None:
            raise NoFreshConsensusDrop(
                f"no ffanalytics drop in {self._dir} (has the rsidecar run?)"
            )
        body = drop.read_text(encoding="utf-8")
        data = json.loads(body)

        version = int(data.get("payload_version", RSIDECAR_PAYLOAD_VERSION))
        if version != RSIDECAR_PAYLOAD_VERSION:
            raise NoFreshConsensusDrop(
                f"{drop.name}: payload_version {version}, expected {RSIDECAR_PAYLOAD_VERSION}"
            )
        if int(data.get("week", week)) != week:
            raise NoFreshConsensusDrop(
                f"{drop.name}: is for week {data.get('week')}, not week {week}"
            )

        age = self._clock() - datetime.fromtimestamp(drop.stat().st_mtime, tz=UTC)
        if age > self._max_age:
            raise NoFreshConsensusDrop(
                f"{drop.name}: {age.days}d old, older than the {self._max_age.days}d limit"
            )

        return RawConsensusPayload(
            source="ffanalytics",
            season=int(data.get("season", season)),
            week=week,
            fetched_at=self._clock(),
            url=drop.as_uri(),
            body=body,
        )

    def _newest_drop(self) -> Path | None:
        if not self._dir.is_dir():
            return None
        drops = sorted(self._dir.glob("*.json"))
        return drops[-1] if drops else None


def build_sleeper_payload(
    raw_projections: Sequence[dict],
    players_index: dict[str, dict],
    *,
    season: int,
    week: int,
    generated_at: datetime | None = None,
) -> dict:
    """Merge Sleeper's ``/projections`` rows with its ``/players`` metadata into
    the flat payload shape ``normalize`` consumes. Pure — unit-tested against a
    recorded Sleeper response; the HTTP calls that feed it are not.
    """
    now = (generated_at or datetime.now(UTC)).isoformat()
    players: list[dict] = []
    for row in raw_projections:
        player_id = str(row.get("player_id") or "")
        stats = row.get("stats") or {}
        if not player_id or not stats:
            continue
        meta = players_index.get(player_id, {})
        name = (
            meta.get("full_name")
            or " ".join(x for x in (meta.get("first_name"), meta.get("last_name")) if x)
            or row.get("player", {}).get("full_name")
            or player_id
        )
        position = (
            row.get("position")
            or meta.get("position")
            or (meta.get("fantasy_positions") or [None])[0]
        )
        team = row.get("team") or meta.get("team")
        source_points = stats.get("pts_std") or stats.get("pts_ppr") or stats.get("pts_half_ppr")
        players.append(
            {
                "name": name,
                "team": team,
                "position": position,
                "sleeper_id": player_id,
                "stats": stats,
                "source_points": source_points,
            }
        )
    return {
        "source": "sleeper",
        "payload_version": 1,
        "season": season,
        "week": week,
        "generated_at": now,
        "players": players,
    }


class SleeperConsensusSource(ConsensusSource):
    """The Week-1 stopgap (spec issue #8): weekly projections from the Sleeper
    public API, which needs no key and no signed-in session.
    """

    source_label = "sleeper"

    def __init__(
        self,
        *,
        api_base: str = SLEEPER_API_BASE,
        stats_base: str = SLEEPER_STATS_BASE,
        clock=None,
        timeout: float = 20.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._stats_base = stats_base.rstrip("/")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timeout = timeout

    def fetch(  # pragma: no cover - HTTP boundary, not unit-tested
        self, season: int, week: int
    ) -> RawConsensusPayload:
        proj_url = (
            f"{self._stats_base}/projections/nfl/{season}/{week}"
            f"?season_type=regular&position[]=" + "&position[]=".join(_SLEEPER_POSITIONS)
        )
        raw = self._get_json(proj_url)
        rows = raw if isinstance(raw, list) else raw.get("projections", [])
        players_index = self._get_json(f"{self._api_base}/v1/players/nfl")
        payload = build_sleeper_payload(
            rows,
            players_index if isinstance(players_index, dict) else {},
            season=season,
            week=week,
            generated_at=self._clock(),
        )
        return RawConsensusPayload(
            source="sleeper",
            season=season,
            week=week,
            fetched_at=self._clock(),
            url=proj_url,
            body=json.dumps(payload, ensure_ascii=False),
        )

    def _get_json(self, url: str):  # pragma: no cover - HTTP boundary
        import urllib.request

        logger.info("sleeper GET %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "deadparrots-dashboard"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


class FallbackConsensusSource(ConsensusSource):
    """Try each source in order; the first that returns a payload wins.

    This is how criteria 1 and 2 of spec issue #8 coexist: the ``ffanalytics``
    sidecar drop is preferred, and Sleeper is the automatic stopgap for Week 1
    and for any later week the sidecar has not refreshed.
    """

    source_label = "consensus-fallback"

    def __init__(self, sources: Sequence[ConsensusSource]) -> None:
        if not sources:
            raise ValueError("FallbackConsensusSource needs at least one source")
        self._sources = tuple(sources)

    def fetch(self, season: int, week: int) -> RawConsensusPayload:
        errors: list[str] = []
        for source in self._sources:
            try:
                return source.fetch(season, week)
            except Exception as exc:  # try the next source, remember why this one failed
                label = getattr(source, "source_label", type(source).__name__)
                logger.warning("consensus source %s unavailable: %s", label, exc)
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
        raise ConsensusSourceError(
            "no consensus source produced a payload — " + " | ".join(errors)
        )


def build_consensus_source(settings: Settings) -> ConsensusSource:
    """The consensus source the scheduled weekly pull uses, per ``settings``."""
    rsidecar = RSidecarConsensusSource(settings.consensus_rsidecar_incoming_dir)
    sleeper = SleeperConsensusSource()
    choice = settings.consensus_source
    if choice == "sleeper":
        return sleeper
    if choice == "rsidecar":
        return rsidecar
    return FallbackConsensusSource([rsidecar, sleeper])


def current_season_week(settings: Settings) -> tuple[int, int]:
    """The NFL season and week the scheduled pull should fetch.

    ``consensus_season`` / ``consensus_week`` pin them for tests and manual runs;
    otherwise nflreadpy resolves the live values (imported here so the wiring
    stays importable without it).
    """
    season = settings.consensus_season
    week = settings.consensus_week
    if season is None or week is None:
        import nflreadpy as nfl

        season = season if season is not None else int(nfl.get_current_season())
        week = week if week is not None else int(nfl.get_current_week())
    return season, week
