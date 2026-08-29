from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# The raw consensus payload and its on-disk archive (spec issue #8; user story
# #63: raw source pulls retained as timestamped files so any recommendation is
# reproducible from source). A payload is always a JSON document — the same
# shape whether the R sidecar's ``ffanalytics`` run produced it or the Sleeper
# public-API stopgap did (docs/adr/0005), so the retained file is the exact
# input ``normalize`` is tested on.

PAYLOAD_CONTENT_TYPE = "application/json"
PAYLOAD_EXTENSION = "json"
PAYLOAD_STEM = "consensus"


@dataclass(frozen=True)
class RawConsensusPayload:
    """What a :class:`~deadparrots.consensus.sources.ConsensusSource` returns.

    ``body`` is the serialized JSON payload exactly as it will be archived and
    exactly as ``normalize`` will parse it. ``source`` is the implementation
    label (``ffanalytics`` or ``sleeper``) — retained for provenance, never
    branched on downstream.
    """

    source: str
    season: int
    week: int
    fetched_at: datetime
    url: str
    body: str
    content_type: str = PAYLOAD_CONTENT_TYPE

    def json(self) -> Any:
        """The parsed JSON body."""
        return json.loads(self.body)


class ConsensusArtifactExistsError(FileExistsError):
    """Refused to overwrite an existing archived payload."""


class ConsensusRawStore:
    """Append-only archive of raw consensus-feed payloads.

    Layout: ``<root>/consensus/<pull_id>/consensus.json``, one directory per
    pull, plus a ``manifest.json`` recording the run. Nothing is ever
    overwritten — a benign fast re-run gets a fresh pull id from the runner.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root) / "consensus"

    @property
    def root(self) -> Path:
        return self._root

    def pull_dir(self, pull_id: str) -> Path:
        return self._root / pull_id

    def payload_path(self, pull_id: str) -> Path:
        return self.pull_dir(pull_id) / f"{PAYLOAD_STEM}.{PAYLOAD_EXTENSION}"

    def manifest_path(self, pull_id: str) -> Path:
        return self.pull_dir(pull_id) / "manifest.json"

    def write(self, pull_id: str, payload: RawConsensusPayload) -> Path:
        """Archive one payload; raise rather than clobber an existing file."""
        path = self.payload_path(pull_id)
        if path.exists():
            raise ConsensusArtifactExistsError(f"refusing to overwrite {path}")
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

    def load_payload(self, pull_id: str) -> RawConsensusPayload | None:
        """Reconstruct an archived payload for replay. Provenance fields that are
        not on disk (``fetched_at``, ``url``) come back from the file itself and
        the manifest; ``normalize`` does not read them.
        """
        path = self.payload_path(pull_id)
        if not path.exists():
            return None
        body = path.read_text(encoding="utf-8")
        data = json.loads(body)
        return RawConsensusPayload(
            source=str(data.get("source", "consensus-replay")),
            season=int(data.get("season", 0)),
            week=int(data.get("week", 0)),
            fetched_at=datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
            url=path.as_uri(),
            body=body,
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
