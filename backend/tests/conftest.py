from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.db import init_sqlite
from deadparrots.ingest.datasets import DatasetSpec

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nflverse"


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
