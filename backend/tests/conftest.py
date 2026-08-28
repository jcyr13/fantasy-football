from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings


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
