from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

# The raw news payload and its on-disk archive (spec issue #15; user story #63:
# raw source pulls retained as timestamped files so any recommendation is
# reproducible from source). One pull fans out across several feeds, so a pull
# directory holds one payload file per source plus a ``manifest.json`` — the
# same shape as the Yahoo assisted pull's per-page layout.

PULL_MANIFEST = "manifest.json"


class NewsPayloadFormat(StrEnum):
    """The wire format of a raw news payload — picks the parser in
    ``normalize.py`` and the file extension in the archive.
    """

    ESPN_API_JSON = "espn-api-json"
    RSS = "rss"

    @property
    def extension(self) -> str:
        return "json" if self is NewsPayloadFormat.ESPN_API_JSON else "xml"

    @property
    def content_type(self) -> str:
        return (
            "application/json"
            if self is NewsPayloadFormat.ESPN_API_JSON
            else "application/rss+xml"
        )


@dataclass(frozen=True)
class RawNewsPayload:
    """What a :class:`~deadparrots.news.sources.NewsSource` returns for one feed.

    ``body`` is the response text exactly as it will be archived and exactly as
    ``normalize`` will parse it. ``source`` is the feed label (``espn-api`` /
    ``espn-rss`` / ``yahoo-rss``) — retained for provenance, never branched on
    downstream.
    """

    source: str
    fmt: NewsPayloadFormat
    fetched_at: datetime
    url: str
    body: str

    @property
    def content_type(self) -> str:
        return self.fmt.content_type

    def json(self) -> Any:
        """The parsed JSON body (ESPN endpoint payloads only)."""
        return json.loads(self.body)


class NewsArtifactExistsError(FileExistsError):
    """Refused to overwrite an existing archived payload."""


class NewsRawStore:
    """Append-only archive of raw news payloads.

    Layout: ``<root>/news/<pull_id>/<source>.<ext>``, one directory per poll,
    plus a ``manifest.json`` recording the run. Nothing is ever overwritten — a
    benign fast re-run gets a fresh pull id from the runner.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root) / "news"

    @property
    def root(self) -> Path:
        return self._root

    def pull_dir(self, pull_id: str) -> Path:
        return self._root / pull_id

    def payload_path(self, pull_id: str, payload: RawNewsPayload) -> Path:
        return self.pull_dir(pull_id) / f"{payload.source}.{payload.fmt.extension}"

    def manifest_path(self, pull_id: str) -> Path:
        return self.pull_dir(pull_id) / PULL_MANIFEST

    def write(self, pull_id: str, payload: RawNewsPayload) -> Path:
        """Archive one feed's payload; raise rather than clobber an existing file."""
        path = self.payload_path(pull_id, payload)
        if path.exists():
            raise NewsArtifactExistsError(f"refusing to overwrite {path}")
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

    def load_manifest(self, pull_id: str) -> dict[str, Any] | None:
        path = self.manifest_path(pull_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_manifest(self) -> dict[str, Any] | None:
        for pull_id in reversed(self.pull_ids()):
            manifest = self.load_manifest(pull_id)
            if manifest is not None:
                return manifest
        return None

    def load_payloads(self, pull_id: str) -> list[RawNewsPayload]:
        """Reconstruct a pull's archived payloads for replay, in the order the
        manifest lists them. Provenance fields not stored separately
        (``fetched_at``, ``url``) come back from the manifest.
        """
        manifest = self.load_manifest(pull_id)
        if manifest is None:
            return []
        out: list[RawNewsPayload] = []
        for entry in manifest.get("sources", []):
            fmt = NewsPayloadFormat(entry["fmt"])
            path = self.pull_dir(pull_id) / f"{entry['source']}.{fmt.extension}"
            if not path.exists():
                continue
            out.append(
                RawNewsPayload(
                    source=str(entry["source"]),
                    fmt=fmt,
                    fetched_at=_parse_dt(entry.get("fetched_at")),
                    url=str(entry.get("url", path.as_uri())),
                    body=path.read_text(encoding="utf-8"),
                )
            )
        return out


def _parse_dt(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
