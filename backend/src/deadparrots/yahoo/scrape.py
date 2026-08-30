from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from ..config import Settings
from .pages import YahooPage, page_path
from .raw import RawYahooPayload
from .source import YahooSource

logger = logging.getLogger(__name__)

# The browser-scrape implementation of the source interface (spec issue #7;
# docs/adr/0001). This is the real network boundary — it drives John's signed-in
# desktop browser session — and is deliberately trivial and **not unit-tested**,
# exactly like ``LiveNflverseSource``. The tested surface is the normalizer,
# fed recorded payloads.


class PageExtractor(Protocol):
    """Drive the signed-in browser to ``url`` and return the structured payload
    scraped from that Yahoo page as a plain dict (the shape ``normalize``
    expects). Implemented against whatever browser automation the desktop app
    exposes; swapped for a Yahoo API client later.
    """

    def __call__(self, page: YahooPage, url: str) -> dict[str, Any]: ...


class BrowserYahooSource(YahooSource):
    """Scrape a Yahoo page via a signed-in browser session."""

    source_label = "yahoo-scrape"
    BASE_URL = "https://football.fantasysports.yahoo.com"

    def __init__(
        self,
        extract: PageExtractor,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._extract = extract
        self._clock = clock

    def fetch(  # pragma: no cover - browser boundary, not unit-tested
        self, page: YahooPage, *, week: int | None = None
    ) -> RawYahooPayload:
        url = self.BASE_URL + page_path(page, week=week)
        logger.info("yahoo scrape: %s", url)
        data = self._extract(page, url)
        return RawYahooPayload(
            page=page,
            source=self.source_label,
            fetched_at=self._clock(),
            url=url,
            body=json.dumps(data, ensure_ascii=False, indent=1),
        )


class HttpPageExtractor:
    """A :class:`PageExtractor` that delegates the scrape to the desktop app's
    local extractor endpoint (issue #41; docs/adr/0016 §3).

    The desktop shell owns the embedded, signed-in Yahoo browser view. Its main
    process exposes a loopback HTTP endpoint that, given a page name and URL,
    drives the webview to that page, reads the payload out of the DOM / the
    embedded JSON blob, and returns it as JSON in the shape ``normalize``
    expects. This class is the backend half of that seam; it does no scraping
    itself. The live call reaches Yahoo only through that shell; the
    request/response contract is covered by a loopback stub in
    ``test_yahoo_scrape_wiring.py``.
    """

    def __init__(self, endpoint_url: str, *, timeout: float = 90.0) -> None:
        self._endpoint = endpoint_url.rstrip("/")
        self._timeout = timeout

    def __call__(self, page: YahooPage, url: str) -> dict[str, Any]:
        request_body = json.dumps({"page": page.value, "url": url}).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(
                f"extractor for {page.value} returned {type(payload).__name__}, "
                "expected a JSON object"
            )
        return payload


def build_yahoo_source(settings: Settings) -> YahooSource | None:
    """The assisted-pull source for a server started from these settings.

    Returns a :class:`BrowserYahooSource` wired to the desktop app's extractor
    endpoint when ``settings.yahoo_extractor_url`` is set, otherwise ``None`` — a
    bare backend with no desktop shell keeps answering ``POST /api/yahoo/pull``
    with 503 (issue #41; docs/adr/0016 §3). A test or an out-of-band capture can
    still inject its own source via ``create_app(yahoo_source=...)``.
    """
    if not settings.yahoo_extractor_url:
        return None
    return BrowserYahooSource(
        HttpPageExtractor(
            settings.yahoo_extractor_url,
            timeout=settings.yahoo_extractor_timeout_seconds,
        )
    )
