from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

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
            content_type="application/json",
            body=json.dumps(data, ensure_ascii=False, indent=1),
        )
