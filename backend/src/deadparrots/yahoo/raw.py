from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .pages import YahooPage

# The raw pull payload and its on-disk archive (spec issue #7: "Raw pull payloads
# are retained as timestamped files"). A payload is the structured extract a
# source hands back for one page — always a JSON document, mirroring how the 2025
# scoring oracle stores its scrape (docs/scoring-oracle-capture.md) rather than
# raw HTML, so the retained file is the exact input the normalizer is tested on.
# ADR 0001 fixes this: the future Yahoo API implementation emits the same JSON
# shapes, so there is only ever one payload format.

PAYLOAD_CONTENT_TYPE = "application/json"
PAYLOAD_EXTENSION = "json"


@dataclass(frozen=True)
class RawYahooPayload:
    """What a :class:`~deadparrots.yahoo.source.YahooSource` returns for one page.

    ``body`` is the serialized JSON payload exactly as it will be archived and
    exactly as ``normalize`` will parse it. ``source`` is the implementation
    label (``yahoo-scrape`` now, ``yahoo-api`` later) — retained for provenance,
    never branched on downstream.
    """

    page: YahooPage
    source: str
    fetched_at: datetime
    url: str
    body: str
    content_type: str = PAYLOAD_CONTENT_TYPE

    def json(self) -> Any:
        """The parsed JSON body."""
        return json.loads(self.body)


class YahooArtifactExistsError(FileExistsError):
    """Refused to overwrite an existing archived payload."""


class YahooRawStore:
    """Append-only archive of raw Yahoo pull payloads.

    Layout: ``<root>/yahoo/<pull_id>/<page>.json``, one directory per pull, plus
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

    def payload_path(self, pull_id: str, page: YahooPage) -> Path:
        return self.pull_dir(pull_id) / f"{page.value}.{PAYLOAD_EXTENSION}"

    def manifest_path(self, pull_id: str) -> Path:
        return self.pull_dir(pull_id) / "manifest.json"

    def write(self, pull_id: str, payload: RawYahooPayload) -> Path:
        """Archive one payload; raise rather than clobber an existing file."""
        path = self.payload_path(pull_id, payload.page)
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
            path = self.payload_path(pull_id, page)
            if path.exists():
                return path
        return None

    def load_payload(self, pull_id: str, page: YahooPage) -> RawYahooPayload | None:
        """Reconstruct an archived payload for replay. Provenance fields that are
        not on disk (``fetched_at``, ``url``) come back as placeholders — the
        normalizer does not read them.
        """
        path = self.payload_path(pull_id, page)
        if not path.exists():
            return None
        return RawYahooPayload(
            page=page,
            source="yahoo-replay",
            fetched_at=datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
            url=path.as_uri(),
            body=path.read_text(encoding="utf-8"),
        )

    def load_manifest(self, pull_id: str) -> dict[str, Any] | None:
        path = self.manifest_path(pull_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_manifest(self) -> dict[str, Any] | None:
        """The manifest of the most recent pull, or ``None`` if nothing is archived."""
        for pull_id in reversed(self.pull_ids()):
            manifest = self.load_manifest(pull_id)
            if manifest is not None:
                return manifest
        return None
