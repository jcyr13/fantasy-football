from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import YAHOO_FIXTURE_DIR
from deadparrots.app import create_app
from deadparrots.config import Settings
from deadparrots.yahoo import __main__ as yahoo_cli
from deadparrots.yahoo.pages import ALL_PAGES, YahooPage
from deadparrots.yahoo.raw import YahooRawStore

# The import pull (issue #55): Yahoo page payloads captured outside the app (a
# Claude in Chrome / Cowork session, a bookmarklet, hand-edited JSON) go through
# the same runner and normalizer as the embedded-browser pull, via
# StaticYahooSource.


def _fixture(name: str) -> dict:
    return json.loads((YAHOO_FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _all_four() -> dict[str, dict]:
    return {page.value: _fixture(page.value) for page in ALL_PAGES}


@pytest.fixture
def import_client(data_dir) -> Iterator[TestClient]:
    """A server with the real weekly data sources and no assisted-pull source —
    an import must not need the desktop app's browser."""
    app = create_app(settings=Settings(data_dir=data_dir))
    with TestClient(app) as test_client:
        yield test_client


# --- POST /api/yahoo/import ----------------------------------------------------


def test_importing_all_four_fixture_pages_serves_the_weekly_view(import_client, data_dir):
    assert import_client.get("/api/weekly").status_code == 503

    resp = import_client.post("/api/yahoo/import", json=_all_four())

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert [p["page"] for p in body["pages"]] == ["matchup", "players", "injuries", "standings"]
    assert body["waiver_priority_needs_manual_entry"] is False
    assert YahooRawStore(data_dir).latest_manifest()["source"] == "yahoo-static"
    assert import_client.get("/api/weekly").status_code == 200


def test_a_partial_import_touches_only_the_supplied_page(import_client, data_dir):
    import_client.post("/api/yahoo/import", json=_all_four())
    store = YahooRawStore(data_dir)
    first_pull = store.pull_ids()[-1]

    resp = import_client.post(
        "/api/yahoo/import", json={"standings": _fixture("standings_no_waiver")}
    )

    body = resp.json()
    assert body["ok"] is True
    assert [p["page"] for p in body["pages"]] == ["standings"]
    assert body["waiver_priority_needs_manual_entry"] is True
    second_pull = store.pull_ids()[-1]
    assert second_pull != first_pull
    assert sorted(p.name for p in store.pull_dir(second_pull).glob("*.json")) == [
        "manifest.json",
        "standings.json",
    ]
    assert store.latest_payload_path(YahooPage.STANDINGS).parent.name == second_pull
    assert store.latest_payload_path(YahooPage.MATCHUP).parent.name == first_pull
    # no failure rows for the pages the import left out
    statuses = import_client.get("/api/yahoo/status").json()["pages"]
    assert all(p["status"] == "ok" for p in statuses)
    assert import_client.get("/api/weekly").status_code == 200


def test_a_malformed_payload_is_a_per_page_failure_not_a_500(import_client):
    resp = import_client.post(
        "/api/yahoo/import",
        json={"matchup": _fixture("matchup"), "standings": {"not_rows": []}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    pages = {p["page"]: p for p in body["pages"]}
    assert pages["matchup"]["status"] == "ok"
    assert pages["standings"]["status"] == "failed"
    assert pages["standings"]["error"].startswith("YahooNormalizationError")


def test_a_malformed_import_does_not_displace_the_last_good_page(import_client):
    import_client.post("/api/yahoo/import", json=_all_four())

    import_client.post("/api/yahoo/import", json={"matchup": {"week": 3, "teams": []}})

    assert import_client.get("/api/weekly").status_code == 200


def test_a_payload_pasted_as_a_string_is_parsed_like_a_file(import_client):
    text = (YAHOO_FIXTURE_DIR / "injuries.json").read_text(encoding="utf-8")

    ok = import_client.post("/api/yahoo/import", json={"injuries": text}).json()
    bad = import_client.post("/api/yahoo/import", json={"injuries": "{not json"}).json()

    assert ok["ok"] is True
    assert bad["pages"][0]["status"] == "failed"


@pytest.mark.parametrize("payload", [{}, {"roster": {"rows": []}}, []])
def test_an_empty_or_unknown_page_import_is_rejected(import_client, payload):
    resp = import_client.post("/api/yahoo/import", json=payload)

    assert resp.status_code == 422


# --- python -m deadparrots.yahoo --import <dir> -------------------------------


@pytest.fixture
def cli_data_dir(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(yahoo_cli, "get_settings", lambda: Settings(data_dir=data))
    return data


def _drop_folder(tmp_path: Path, files: dict[str, str]) -> Path:
    folder = tmp_path / "drop"
    folder.mkdir()
    for name, fixture in files.items():
        shutil.copy(YAHOO_FIXTURE_DIR / f"{fixture}.json", folder / f"{name}.json")
    return folder


def test_cli_imports_a_folder_of_page_files(tmp_path, cli_data_dir, capsys):
    folder = _drop_folder(tmp_path, {p.value: p.value for p in ALL_PAGES})

    assert yahoo_cli.main(["--import", str(folder)]) == 0

    manifest = YahooRawStore(cli_data_dir).latest_manifest()
    assert manifest["source"] == "yahoo-static"
    assert set(manifest["pages"]) == {"matchup", "players", "injuries", "standings"}
    assert "import of" in capsys.readouterr().out


def test_cli_imports_only_the_files_present(tmp_path, cli_data_dir):
    folder = _drop_folder(tmp_path, {"standings": "standings"})

    assert yahoo_cli.main(["--import", str(folder)]) == 0

    assert set(YahooRawStore(cli_data_dir).latest_manifest()["pages"]) == {"standings"}


def test_cli_import_exits_non_zero_on_any_page_failure(tmp_path, cli_data_dir, capsys):
    folder = _drop_folder(tmp_path, {"matchup": "matchup"})
    (folder / "standings.json").write_text('{"not_rows": []}', encoding="utf-8")

    assert yahoo_cli.main(["--import", str(folder)]) == 1
    assert "failed" in capsys.readouterr().out


def test_cli_import_refuses_a_week(tmp_path, cli_data_dir):
    folder = _drop_folder(tmp_path, {"standings": "standings"})

    with pytest.raises(SystemExit):
        yahoo_cli.main(["--import", str(folder), "--week", "3"])


def test_cli_import_exits_non_zero_when_the_folder_has_no_page_files(
    tmp_path, cli_data_dir, capsys
):
    empty = tmp_path / "empty"
    empty.mkdir()

    assert yahoo_cli.main(["--import", str(empty)]) == 2
    assert yahoo_cli.main(["--import", str(tmp_path / "missing")]) == 2
    assert "matchup.json" in capsys.readouterr().out
    assert YahooRawStore(cli_data_dir).pull_ids() == []
