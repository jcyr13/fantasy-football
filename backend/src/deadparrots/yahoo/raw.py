from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .pages import ALL_PAGES, YahooPage

# The raw pull payload and its on-disk archive (spec issue #7: "Raw pull payloads
# are retained as timestamped files"). A payload is the structured extract a
# source hands back for one page — a JSON document, mirroring how the 2025
# scoring oracle stores its scrape (docs/scoring-oracle-capture.md) rather than
# raw HTML, so the retained file is the exact input the normalizer is tested on.

_EXTENSION_BY_CONTENT_TYPE = {
    "application/json": "json",
    "text/html": "html",
}


@dataclass(frozen=True)
class RawYahooPayload:
    """What a :class:`~deadparrots.yahoo.source.YahooSource` returns for one page.

    ``body`` is the serialized payload exactly as it will be archived and exactly
    as ``normalize`` will parse it. ``source`` is the implementation label
    (``yahoo-scrape`` now, ``yahoo-api`` later) — retained for provenance, never
    branched on downstream.
    """

    page: YahooPage
    source: str
    fetched_at: datetime
    url: str
    content_type: str
    body: str

    @property
    def extension(self) -> str:
        return _EXTENSION_BY_CONTENT_TYPE.get(self.content_type, "txt")

    def json(self) -> Any:
        """The parsed JSON body. Raises if this payload is not JSON."""
        if self.content_type != "application/json":
            raise ValueError(f"{self.page.value}: payload is {self.content_type}, not JSON")
        return json.loads(self.body)


class YahooArtifactExistsError(FileExistsError):
    """Refused to overwrite an existing archived payload."""


class YahooRawStore:
    """Append-only archive of raw Yahoo pull payloads.

    Layout: ``<root>/yahoo/<pull_id>/<page>.<ext>``, one directory per pull, plus
    a ``manifest.json`` recording the run. Nothing is ever overwritten — a benign
    fast re-run gets a fresh pull id from the runner instead.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root) / "yahoo"

    @property
    def root(self) -> Path:
        return self._root

    def pull_dir(self, pull_id: str) -> Path:
        return self._root / pull_id

    def payload_path(self, pull_id: str, page: YahooPage, extension: str = "json") -> Path:
        return self.pull_dir(pull_id) / f"{page.value}.{extension}"

    def manifest_path(self, pull_id: str) -> Path:
        return self.pull_dir(pull_id) / "manifest.json"

    def write(self, pull_id: str, payload: RawYahooPayload) -> Path:
        """Archive one payload; raise rather than clobber an existing file."""
        path = self.payload_path(pull_id, payload.page, payload.extension)
        if path.exists():
            raise YahooArtifactExistsError(f"refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.body, encoding="utf-8")
        return path

    def write_manifest(self, pull_id: str, manifest: dict[str, Any]) -> Path:
        path = self.manifest_path(pull_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def pull_ids(self) -> list[str]:
        """Every pull id present, oldest first (ids sort chronologically)."""
        if not self._root.exists():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir())

    def latest_payload_path(self, page: YahooPage) -> Path | None:
        for pull_id in reversed(self.pull_ids()):
            for extension in _EXTENSION_BY_CONTENT_TYPE.values():
                path = self.payload_path(pull_id, page, extension)
                if path.exists():
                    return path
        return None

    def load_payload(self, pull_id: str, page: YahooPage) -> RawYahooPayload | None:
        """Reconstruct an archived payload for replay. Provenance fields that are
        not on disk (``fetched_at``, ``url``) come back as placeholders — the
        normalizer does not read them.
        """
        for content_type, extension in _EXTENSION_BY_CONTENT_TYPE.items():
            path = self.payload_path(pull_id, page, extension)
            if path.exists():
                return RawYahooPayload(
                    page=page,
                    source="yahoo-replay",
                    fetched_at=datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
                    url=path.as_uri(),
                    content_type=content_type,
                    body=path.read_text(encoding="utf-8"),
                )
        return None


def missing_pages(store: YahooRawStore, pull_id: str) -> list[YahooPage]:
    """Pages with no archived payload in ``pull_id`` — a partial pull."""
    return [p for p in ALL_PAGES if store.load_payload(pull_id, p) is None]
