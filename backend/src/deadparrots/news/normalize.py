from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .raw import NewsPayloadFormat, RawNewsPayload

# recorded-payload-in -> normalized-articles-out (spec issue #15: "Source
# payload -> normalized items is covered by a recorded-payload test"). Every
# ``normalize_*`` function here is pure: a recorded response body in, a list of
# ``ParsedArticle`` out, no I/O. The HTTP fetch that produces the body is a
# separate seam (``sources.py``) and is not unit-tested — exactly like
# ``LiveNflverseSource`` / ``BrowserYahooSource`` / ``SleeperConsensusSource``.
#
# A ``ParsedArticle`` is the raw material for a ``NewsItem``: it has no player
# tags and no bucket yet. Tagging (``tagging.py``) and the 48-hour window +
# dedupe (``feed.py``) run after this.

# Atom / RSS namespaces some feeds decorate their elements with.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class ParsedArticle:
    """One news article, normalized out of a source payload but not yet tagged.

    ``published_at`` is always tz-aware UTC. ``summary`` is the feed's blurb with
    surrounding whitespace collapsed, or ``None`` when the feed gives none.
    ``source`` is the feed label the payload carried.
    """

    title: str
    url: str
    summary: str | None
    source: str
    published_at: datetime


class NewsNormalizationError(ValueError):
    """A recorded news payload is missing structure the parser depends on."""

    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"{source}: {message}")


def normalize_payload(payload: RawNewsPayload) -> list[ParsedArticle]:
    """Parse one raw payload into its articles, dispatching on the wire format.

    An empty article list is not an error — a feed can legitimately have nothing
    fresh. Malformed *structure* (unparseable JSON/XML, a missing top-level
    container) raises :class:`NewsNormalizationError`.
    """
    if payload.fmt is NewsPayloadFormat.ESPN_API_JSON:
        return _normalize_espn_api(payload)
    if payload.fmt is NewsPayloadFormat.RSS:
        return _normalize_rss(payload)
    raise NewsNormalizationError(payload.source, f"unknown payload format {payload.fmt!r}")


def normalize_payloads(payloads: list[RawNewsPayload]) -> list[ParsedArticle]:
    """Every payload's articles, concatenated in payload order."""
    out: list[ParsedArticle] = []
    for payload in payloads:
        out.extend(normalize_payload(payload))
    return out


# --- ESPN keyless news endpoint -------------------------------------------


def _normalize_espn_api(payload: RawNewsPayload) -> list[ParsedArticle]:
    try:
        data = json.loads(payload.body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise NewsNormalizationError(
            payload.source, f"payload is not valid JSON ({exc})"
        ) from exc
    if not isinstance(data, dict) or "articles" not in data:
        raise NewsNormalizationError(payload.source, "payload has no 'articles' array")
    articles = data.get("articles")
    if not isinstance(articles, list):
        raise NewsNormalizationError(payload.source, "'articles' is not a list")

    out: list[ParsedArticle] = []
    for entry in articles:
        if not isinstance(entry, dict):
            continue
        title = _clean(entry.get("headline") or entry.get("title"))
        url = _espn_link(entry)
        if not title or not url:
            continue
        published = _parse_iso(entry.get("published") or entry.get("lastModified"))
        if published is None:
            continue
        out.append(
            ParsedArticle(
                title=title,
                url=url,
                summary=_clean(entry.get("description")) or None,
                source=payload.source,
                published_at=published,
            )
        )
    return out


def _espn_link(entry: dict) -> str:
    links = entry.get("links")
    if isinstance(links, dict):
        for key in ("web", "mobile"):
            block = links.get(key)
            if isinstance(block, dict):
                href = _clean(block.get("href"))
                if href:
                    return href
    return _clean(entry.get("link"))


# --- RSS 2.0 feeds (ESPN NFL, Yahoo Sports NFL) --------------------------


def _normalize_rss(payload: RawNewsPayload) -> list[ParsedArticle]:
    try:
        root = ET.fromstring(payload.body)
    except ET.ParseError as exc:
        raise NewsNormalizationError(
            payload.source, f"payload is not valid XML ({exc})"
        ) from exc

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall("item")
    if channel is None and not items:
        # An Atom feed uses <entry> under the document root.
        items = root.findall(f"{_ATOM_NS}entry")
        if not items:
            raise NewsNormalizationError(
                payload.source, "payload has no <channel>/<item> or <entry> elements"
            )

    out: list[ParsedArticle] = []
    for item in items:
        title = _clean(_rss_text(item, "title"))
        url = _rss_link(item)
        if not title or not url:
            continue
        published = _parse_rss_date(
            _rss_text(item, "pubDate")
            or _rss_text(item, "published")
            or _rss_text(item, "updated")
            or _rss_text(item, f"{_ATOM_NS}updated")
        )
        if published is None:
            continue
        summary = _clean(
            _rss_text(item, "description") or _rss_text(item, f"{_ATOM_NS}summary")
        )
        out.append(
            ParsedArticle(
                title=title,
                url=url,
                summary=summary or None,
                source=payload.source,
                published_at=published,
            )
        )
    return out


def _rss_text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return child.text if child is not None and child.text else ""


def _rss_link(item: ET.Element) -> str:
    link = item.find("link")
    if link is not None and link.text and link.text.strip():
        return link.text.strip()
    # Atom: <link href="..."/>, preferring rel="alternate".
    atom_links = item.findall(f"{_ATOM_NS}link")
    for candidate in atom_links:
        if candidate.get("rel", "alternate") == "alternate" and candidate.get("href"):
            return candidate.get("href", "").strip()
    if atom_links and atom_links[0].get("href"):
        return atom_links[0].get("href", "").strip()
    guid = item.find("guid")
    if guid is not None and guid.text and guid.text.strip().startswith("http"):
        return guid.text.strip()
    return ""


# --- shared helpers -----------------------------------------------------


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _parse_iso(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_rss_date(value: str) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return _parse_iso(text)
    if parsed is None:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
