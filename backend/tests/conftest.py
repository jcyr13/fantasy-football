from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.consensus.raw import ConsensusRawStore, RawConsensusPayload
from deadparrots.db import init_sqlite
from deadparrots.ingest.datasets import DatasetSpec
from deadparrots.news.raw import NewsPayloadFormat, NewsRawStore, RawNewsPayload
from deadparrots.news.tagging import NewsTargets
from deadparrots.yahoo.pages import YahooPage
from deadparrots.yahoo.raw import RawYahooPayload, YahooRawStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nflverse"
YAHOO_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "yahoo"
CONSENSUS_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "consensus"
NEWS_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "news"


@pytest.fixture(autouse=True)
def _no_launch_catchup(monkeypatch) -> None:
    """Neutralize the on-launch catch-up sweep (issue #41) for tests.

    The real sweep bumps ``next_run_time`` on the nflverse / consensus / news
    jobs, which would fire live network pulls the instant a ``TestClient``
    enters the app lifespan. ``app.py`` imports ``deadparrots.catchup`` lazily,
    so patching the function on the module is enough. The catch-up tests call
    the real functions directly.
    """
    monkeypatch.setattr(
        "deadparrots.catchup.run_catchup_on_launch", lambda *a, **k: []
    )


@pytest.fixture
def data_dir(tmp_path) -> Path:
    """Where the app-state and analytics stores live for a test."""
    return tmp_path / "data"


@pytest.fixture
def client(data_dir) -> Iterator[TestClient]:
    """A TestClient whose stores live under ``data_dir``.

    Entering the context manager runs the app's lifespan, so the SQLite and
    DuckDB files are created exactly as they would be in a real startup.
    """
    app = create_app(settings=Settings(data_dir=data_dir))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sqlite_conn(tmp_path) -> Iterator[sqlite3.Connection]:
    """A real, initialized SQLite app-state connection on a temp file."""
    conn = init_sqlite(tmp_path / "app.sqlite")
    try:
        yield conn
    finally:
        conn.close()


def load_raw_nflverse(name: str) -> pl.DataFrame:
    """A recorded raw nflverse payload, as ``nflreadpy`` would hand it back."""
    rows = json.loads((FIXTURE_DIR / f"{name}.json").read_text())
    return pl.DataFrame(rows, infer_schema_length=None)


@pytest.fixture
def raw_nflverse():
    """Factory: ``raw_nflverse("pbp")`` -> the recorded raw payload for a dataset."""
    return load_raw_nflverse


class FakeNflverseSource:
    """A source backed by recorded fixtures; a dataset name in ``fail_for`` raises."""

    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.loaded: list[str] = []

    def load(self, spec: DatasetSpec) -> pl.DataFrame:
        self.loaded.append(spec.name)
        if spec.name in self.fail_for:
            raise RuntimeError(f"simulated nflverse outage for {spec.name}")
        fixture = "player_stats" if spec.name == "idp" else spec.name
        return load_raw_nflverse(fixture)


class RecordingAlerter:
    """Captures the alert messages the runner would have emailed."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> None:
        self.messages.append((subject, body))


@pytest.fixture
def fake_source() -> FakeNflverseSource:
    return FakeNflverseSource()


@pytest.fixture
def make_fake_source():
    """Factory: ``make_fake_source(fail_for={"schedules"})``."""

    def _make(*, fail_for: set[str] | None = None) -> FakeNflverseSource:
        return FakeNflverseSource(fail_for=fail_for)

    return _make


@pytest.fixture
def recording_alerter() -> RecordingAlerter:
    return RecordingAlerter()


# --- Yahoo assisted pull (issue #7) -----------------------------------------


def load_yahoo_payload(page: YahooPage, name: str | None = None) -> RawYahooPayload:
    """A recorded structured payload for one Yahoo page, wrapped as a
    ``RawYahooPayload`` exactly as a source would return it. ``name`` overrides
    the fixture file stem (e.g. ``"standings_no_waiver"``).
    """
    body = (YAHOO_FIXTURE_DIR / f"{name or page.value}.json").read_text(encoding="utf-8")
    return RawYahooPayload(
        page=page,
        source="yahoo-fixture",
        fetched_at=datetime(2026, 9, 22, 13, 0, 0, tzinfo=UTC),
        url=f"https://example.test/{page.value}",
        body=body,
    )


@pytest.fixture
def yahoo_payload():
    """Factory: ``yahoo_payload(YahooPage.MATCHUP)`` -> recorded ``RawYahooPayload``."""
    return load_yahoo_payload


class FakeYahooSource:
    """A source backed by the recorded Yahoo fixtures; a page in ``fail_for``
    raises, and ``payload_names`` swaps in an alternate fixture file per page.
    """

    source_label = "yahoo-fake"

    def __init__(
        self,
        *,
        fail_for: set[YahooPage] | None = None,
        payload_names: dict[YahooPage, str] | None = None,
    ) -> None:
        self.fail_for = fail_for or set()
        self.payload_names = payload_names or {}
        self.fetched: list[YahooPage] = []

    def fetch(self, page: YahooPage, *, week: int | None = None) -> RawYahooPayload:
        self.fetched.append(page)
        if page in self.fail_for:
            raise RuntimeError(f"simulated Yahoo scrape failure for {page.value}")
        return load_yahoo_payload(page, self.payload_names.get(page))


@pytest.fixture
def fake_yahoo_source() -> FakeYahooSource:
    return FakeYahooSource()


@pytest.fixture
def make_fake_yahoo_source():
    """Factory: ``make_fake_yahoo_source(fail_for={YahooPage.INJURIES})``."""

    def _make(
        *,
        fail_for: set[YahooPage] | None = None,
        payload_names: dict[YahooPage, str] | None = None,
    ) -> FakeYahooSource:
        return FakeYahooSource(fail_for=fail_for, payload_names=payload_names)

    return _make


@pytest.fixture
def yahoo_raw_store(tmp_path) -> YahooRawStore:
    return YahooRawStore(tmp_path / "data")


# --- consensus feed sidecar (issue #8) -------------------------------------


def load_consensus_payload(name: str) -> RawConsensusPayload:
    """A recorded consensus payload (an ``ffanalytics`` sidecar drop or a
    Sleeper stopgap response), wrapped exactly as a source would return it.
    """
    body = (CONSENSUS_FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    data = json.loads(body)
    return RawConsensusPayload(
        source=str(data["source"]),
        season=int(data["season"]),
        week=int(data["week"]),
        fetched_at=datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC),
        url=f"https://example.test/consensus/{name}",
        body=body,
    )


@pytest.fixture
def consensus_payload():
    """Factory: ``consensus_payload("ffanalytics_week1")`` -> ``RawConsensusPayload``."""
    return load_consensus_payload


class FakeConsensusSource:
    """A source backed by a recorded consensus fixture; ``fail_with`` raises."""

    def __init__(
        self, name: str = "ffanalytics_week1", *, fail_with: Exception | None = None
    ) -> None:
        self._name = name
        self._fail_with = fail_with
        self.calls: list[tuple[int, int]] = []

    @property
    def source_label(self) -> str:
        return "consensus-fake"

    def fetch(self, season: int, week: int) -> RawConsensusPayload:
        self.calls.append((season, week))
        if self._fail_with is not None:
            raise self._fail_with
        return load_consensus_payload(self._name)


@pytest.fixture
def make_fake_consensus_source():
    """Factory: ``make_fake_consensus_source("sleeper_week1", fail_with=...)``."""

    def _make(
        name: str = "ffanalytics_week1", *, fail_with: Exception | None = None
    ) -> FakeConsensusSource:
        return FakeConsensusSource(name, fail_with=fail_with)

    return _make


@pytest.fixture
def fake_consensus_source() -> FakeConsensusSource:
    return FakeConsensusSource()


@pytest.fixture
def consensus_raw_store(tmp_path) -> ConsensusRawStore:
    return ConsensusRawStore(tmp_path / "data")


# --- news module (issue #15) ---------------------------------------------

_NEWS_FIXTURES: dict[str, tuple[NewsPayloadFormat, str]] = {
    "espn_api_news": (NewsPayloadFormat.ESPN_API_JSON, "espn-api"),
    "espn_rss": (NewsPayloadFormat.RSS, "espn-rss"),
    "yahoo_rss": (NewsPayloadFormat.RSS, "yahoo-rss"),
}


def load_news_payload(name: str, *, source: str | None = None) -> RawNewsPayload:
    """A recorded news feed body (ESPN endpoint JSON or an RSS feed), wrapped
    exactly as a :class:`~deadparrots.news.sources.NewsSource` would return it.
    """
    fmt, default_source = _NEWS_FIXTURES[name]
    path = NEWS_FIXTURE_DIR / f"{name}.{fmt.extension}"
    return RawNewsPayload(
        source=source or default_source,
        fmt=fmt,
        fetched_at=datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC),
        url=f"https://example.test/news/{name}",
        body=path.read_text(encoding="utf-8"),
    )


@pytest.fixture
def news_payload():
    """Factory: ``news_payload("espn_api_news")`` -> ``RawNewsPayload``."""
    return load_news_payload


class FakeNewsSource:
    """A source backed by a recorded news fixture; ``fail_with`` raises."""

    def __init__(
        self,
        name: str = "espn_api_news",
        *,
        source_label: str | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self._name = name
        self.source_label = source_label or _NEWS_FIXTURES[name][1]
        self._fail_with = fail_with
        self.calls = 0

    def fetch(self) -> list[RawNewsPayload]:
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
        return [load_news_payload(self._name, source=self.source_label)]


@pytest.fixture
def make_fake_news_source():
    """Factory: ``make_fake_news_source("espn_rss", fail_with=...)``."""

    def _make(
        name: str = "espn_api_news",
        *,
        source_label: str | None = None,
        fail_with: Exception | None = None,
    ) -> FakeNewsSource:
        return FakeNewsSource(name, source_label=source_label, fail_with=fail_with)

    return _make


@pytest.fixture
def news_raw_store(tmp_path) -> NewsRawStore:
    return NewsRawStore(tmp_path / "data")


@pytest.fixture
def news_targets() -> NewsTargets:
    """The three target lists used across the news tests. ``Rashee Rice`` and
    ``Jaylen Warren`` are the free-agent shortlist; the rosters split the rest.
    """
    return NewsTargets(
        my_roster=("Josh Allen", "Bijan Robinson", "Ja'Marr Chase"),
        opponent=("Patrick Mahomes", "Tyreek Hill"),
        free_agents=("Rashee Rice", "Jaylen Warren"),
    )
