from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .raw import NewsPayloadFormat, RawNewsPayload

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# The single interface every news fetch goes through (spec issue #15). ESPN's
# keyless NFL news endpoint is the primary source; the ESPN NFL and Yahoo Sports
# NFL RSS feeds are the secondaries. Nothing downstream of a source knows which
# feed answered — the payload's ``source`` label is provenance, not a branch.
#
# The fetch itself (HTTP GET, reading the response body) is never unit-tested —
# only the recorded-payload -> ``ParsedArticle`` path is, exactly like
# ``LiveNflverseSource`` / ``BrowserYahooSource`` / ``SleeperConsensusSource``.

_USER_AGENT = "deadparrots-dashboard (+https://github.com/jcyr13/fantasy-football)"
_DEFAULT_TIMEOUT = 15.0


class NewsSourceError(RuntimeError):
    """A news feed could not be fetched."""


class NewsSource:
    """Return raw payloads for one news feed. Implementations own the transport
    (an HTTP GET against a keyless endpoint or an RSS URL); they do not parse,
    tag, or dedupe.
    """

    source_label: str = "news"

    def fetch(self) -> list[RawNewsPayload]:
        raise NotImplementedError  # pragma: no cover - interface


class StaticNewsSource(NewsSource):
    """Serve a fixed set of payloads. For wiring a poll from bodies captured out
    of band (a replayed archive, a desktop capture) and for tests.
    """

    source_label = "news-static"

    def __init__(self, payloads: Sequence[RawNewsPayload]) -> None:
        self._payloads = tuple(payloads)

    def fetch(self) -> list[RawNewsPayload]:
        return list(self._payloads)


class EspnNewsApiSource(NewsSource):
    """ESPN's keyless NFL news endpoint — the primary source (spec issue #15).

    No key, no session. Returns a single JSON payload.
    """

    source_label = "espn-api"
    DEFAULT_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"

    def __init__(
        self, *, url: str = DEFAULT_URL, clock=None, timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        self._url = url
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timeout = timeout

    def fetch(self) -> list[RawNewsPayload]:  # pragma: no cover - HTTP boundary
        body = _http_get(self._url, self._timeout)
        # Fail fast on a body that is not the JSON envelope we expect, so the
        # runner records this feed failed rather than archiving garbage.
        try:
            json.loads(body)
        except ValueError as exc:
            raise NewsSourceError(f"{self.source_label}: response was not JSON ({exc})")
        return [
            RawNewsPayload(
                source=self.source_label,
                fmt=NewsPayloadFormat.ESPN_API_JSON,
                fetched_at=self._clock(),
                url=self._url,
                body=body,
            )
        ]


class RssNewsSource(NewsSource):
    """An RSS 2.0 feed — ESPN NFL or Yahoo Sports NFL (spec issue #15)."""

    def __init__(
        self,
        *,
        source_label: str,
        feed_url: str,
        clock=None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.source_label = source_label
        self._url = feed_url
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timeout = timeout

    def fetch(self) -> list[RawNewsPayload]:  # pragma: no cover - HTTP boundary
        body = _http_get(self._url, self._timeout)
        return [
            RawNewsPayload(
                source=self.source_label,
                fmt=NewsPayloadFormat.RSS,
                fetched_at=self._clock(),
                url=self._url,
                body=body,
            )
        ]


def _http_get(url: str, timeout: float) -> str:  # pragma: no cover - HTTP boundary
    import urllib.request

    logger.info("news GET %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def build_news_sources(settings: Settings) -> tuple[NewsSource, ...]:
    """The feeds the scheduled poll pulls, per ``settings``. A blank URL
    disables that feed.
    """
    sources: list[NewsSource] = []
    if settings.news_espn_api_url:
        sources.append(EspnNewsApiSource(url=settings.news_espn_api_url))
    if settings.news_espn_rss_url:
        sources.append(
            RssNewsSource(source_label="espn-rss", feed_url=settings.news_espn_rss_url)
        )
    if settings.news_yahoo_rss_url:
        sources.append(
            RssNewsSource(source_label="yahoo-rss", feed_url=settings.news_yahoo_rss_url)
        )
    return tuple(sources)
