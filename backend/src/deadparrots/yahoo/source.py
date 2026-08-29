from __future__ import annotations

from datetime import UTC, datetime

from .pages import YahooPage, page_path
from .raw import RawYahooPayload, YahooRawStore

# The single interface every bit of Yahoo access goes through (spec issue #7;
# docs/adr/0001). A browser scrape backs it in v1; the official Yahoo Fantasy
# API drops in later as another implementation with no change to the runner, the
# normalizer, or anything downstream. The fetch itself is never unit-tested —
# only the recorded-payload -> normalized-objects path is.


class YahooSource:
    """Return a raw payload for one Yahoo page. Implementations own the transport
    (a signed-in browser session, or the API); they do not normalize.
    """

    source_label: str = "yahoo"

    def fetch(self, page: YahooPage, *, week: int | None = None) -> RawYahooPayload:
        raise NotImplementedError  # pragma: no cover - interface


class ReplayYahooSource(YahooSource):
    """Serve payloads from a previously archived pull instead of the network.

    The point of the source interface is that nothing downstream can tell the
    difference — so replaying a captured pull is a first-class way to develop and
    test the layers built on top of the assisted pull (spec issues #11-#15)
    without a live Yahoo session.
    """

    source_label = "yahoo-replay"

    def __init__(self, store: YahooRawStore, pull_id: str) -> None:
        self._store = store
        self._pull_id = pull_id

    def fetch(self, page: YahooPage, *, week: int | None = None) -> RawYahooPayload:
        payload = self._store.load_payload(self._pull_id, page)
        if payload is None:
            raise FileNotFoundError(
                f"no archived {page.value} payload in pull {self._pull_id}"
            )
        return payload


class StaticYahooSource(YahooSource):
    """Serve a fixed set of in-memory payload bodies keyed by page. Handy for
    wiring a pull from payloads captured out-of-band (e.g. by the desktop app's
    browser view) without going through the archive first.
    """

    source_label = "yahoo-static"

    def __init__(
        self,
        bodies: dict[YahooPage, str],
        *,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._bodies = bodies
        self._clock = clock

    def fetch(self, page: YahooPage, *, week: int | None = None) -> RawYahooPayload:
        if page not in self._bodies:
            raise FileNotFoundError(f"no payload supplied for {page.value}")
        return RawYahooPayload(
            page=page,
            source=self.source_label,
            fetched_at=self._clock(),
            url=page_path(page, week=week),
            body=self._bodies[page],
        )
