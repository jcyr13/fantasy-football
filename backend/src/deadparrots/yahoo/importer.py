from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path

from .pages import ALL_PAGES, YahooPage
from .raw import PAYLOAD_EXTENSION, YahooRawStore
from .runner import YahooPullRun, run_yahoo_pull
from .source import StaticYahooSource

# The import pull (issue #55): a fallback for when the embedded-browser pull
# breaks. Page payloads captured outside the app — a Claude in Chrome / Cowork
# session, a bookmarklet, hand-edited JSON — run through the same runner and
# normalizer as a live pull, served by ``StaticYahooSource`` so the manifest
# records ``yahoo-static``. Only the supplied pages are pulled, so a partial
# import records no failures for the pages it left out. See
# docs/yahoo-import.md for the payload shapes.


class YahooImportError(ValueError):
    """Nothing importable was supplied."""


def import_yahoo_pages(
    bodies: Mapping[YahooPage, str],
    *,
    raw_store: YahooRawStore,
    conn: sqlite3.Connection,
) -> YahooPullRun:
    """Archive and normalize each supplied page body as one pull set."""
    if not bodies:
        raise YahooImportError("no Yahoo page payloads supplied")
    return run_yahoo_pull(
        source=StaticYahooSource(dict(bodies)),
        raw_store=raw_store,
        conn=conn,
        pages=[page for page in ALL_PAGES if page in bodies],
    )


def read_import_dir(directory: Path) -> dict[YahooPage, str]:
    """The ``<page>.json`` bodies present in ``directory``, keyed by page."""
    names = ", ".join(f"{page.value}.{PAYLOAD_EXTENSION}" for page in ALL_PAGES)
    if not directory.is_dir():
        raise YahooImportError(f"{directory} is not a folder (expected {names})")
    bodies = {
        page: path.read_text(encoding="utf-8")
        for page in ALL_PAGES
        if (path := directory / f"{page.value}.{PAYLOAD_EXTENSION}").is_file()
    }
    if not bodies:
        raise YahooImportError(f"no page files in {directory} (expected {names})")
    return bodies
