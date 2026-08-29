from __future__ import annotations

from enum import StrEnum

# The four Yahoo pages the assisted pull scrapes for the RIP TIDE League
# (spec issue #7). Yahoo assigns a new league id per season; 2026 is 735806
# (2025 was 195010 — see docs/scoring-oracle-capture.md).

LEAGUE_ID = "735806"


class YahooPage(StrEnum):
    """One scraped Yahoo page. The value doubles as the on-disk file stem and the
    ``pull_status`` dataset label.
    """

    MATCHUP = "matchup"
    PLAYERS = "players"
    INJURIES = "injuries"
    STANDINGS = "standings"

    @property
    def source(self) -> str:
        """Stable ``yahoo_pull_status`` source label, e.g. ``yahoo:matchup``."""
        return f"yahoo:{self.value}"


ALL_PAGES: tuple[YahooPage, ...] = tuple(YahooPage)


def page_path(page: YahooPage, *, week: int | None = None) -> str:
    """The league-relative Yahoo path for a page, e.g. ``/f1/735806/matchup``.

    ``week`` is only meaningful for the matchup page; Yahoo ignores it elsewhere,
    so it is appended only there.
    """
    path = f"/f1/{LEAGUE_ID}/{page.value}"
    if week is not None and page is YahooPage.MATCHUP:
        path = f"{path}?week={week}"
    return path
