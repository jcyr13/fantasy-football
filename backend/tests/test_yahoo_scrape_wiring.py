"""Wiring the assisted pull to the desktop app's Yahoo extractor endpoint
(issue #41).

The desktop shell owns the signed-in Yahoo browser view and exposes a loopback
HTTP endpoint that scrapes one page per call. ``build_yahoo_source`` turns
``DEADPARROTS_YAHOO_EXTRACTOR_URL`` into a wired ``BrowserYahooSource``; with it
set, ``POST /api/yahoo/pull`` runs the real pull instead of answering 503.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.yahoo.scrape import BrowserYahooSource, build_yahoo_source

FIXTURES = Path(__file__).parent / "fixtures" / "yahoo"


def test_build_yahoo_source_is_none_without_an_extractor_url():
    assert build_yahoo_source(Settings()) is None


def test_build_yahoo_source_wires_a_browser_source_when_configured():
    source = build_yahoo_source(
        Settings(yahoo_extractor_url="http://127.0.0.1:9/scrape")
    )

    assert isinstance(source, BrowserYahooSource)
    assert source.source_label == "yahoo-scrape"


class _ExtractorHandler(BaseHTTPRequestHandler):
    """Stands in for the desktop app: returns the recorded fixture body for the
    requested page. ``standings`` is swapped for the no-waiver-column fixture
    when the server was started with ``no_waiver=True``."""

    no_waiver = False

    def log_message(self, *args):  # silence the default stderr spew
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        page = body["page"]
        stem = (
            "standings_no_waiver"
            if page == "standings" and self.no_waiver
            else page
        )
        payload = (FIXTURES / f"{stem}.json").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def extractor_url() -> Iterator[str]:
    yield from _serve(no_waiver=False)


@pytest.fixture
def no_waiver_extractor_url() -> Iterator[str]:
    yield from _serve(no_waiver=True)


def _serve(*, no_waiver: bool) -> Iterator[str]:
    handler = type("_H", (_ExtractorHandler,), {"no_waiver": no_waiver})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/scrape"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def pull_client(data_dir, extractor_url) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(data_dir=data_dir, yahoo_extractor_url=extractor_url)
    )
    with TestClient(app) as client:
        yield client


def test_pull_succeeds_end_to_end_against_the_extractor_endpoint(
    pull_client, data_dir
):
    resp = pull_client.post("/api/yahoo/pull")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert {p["page"] for p in body["pages"]} == {
        "matchup",
        "players",
        "injuries",
        "standings",
    }
    assert all(p["status"] == "ok" for p in body["pages"])
    assert body["waiver_priority_needs_manual_entry"] is False

    # raw payloads archived under the local data dir, plus a manifest
    pull_dir = data_dir / "yahoo" / body["pull_id"]
    assert (pull_dir / "matchup.json").is_file()
    assert (pull_dir / "manifest.json").is_file()

    # the freshness header leaves "never" after a successful pull
    status = pull_client.get("/api/yahoo/status").json()
    assert status["last_successful_pull"] is not None
    assert status["reminder"] is None


def test_missing_waiver_priority_still_flags_for_manual_entry(
    data_dir, no_waiver_extractor_url
):
    app = create_app(
        settings=Settings(
            data_dir=data_dir, yahoo_extractor_url=no_waiver_extractor_url
        )
    )
    with TestClient(app) as client:
        pulled = client.post("/api/yahoo/pull").json()
        assert pulled["ok"] is True
        assert pulled["waiver_priority_needs_manual_entry"] is True
