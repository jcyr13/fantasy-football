from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# The normalized News domain objects (spec issue #15; CONTEXT.md "News ticker").
# Everything downstream of the source interface consumes these and never sees a
# raw payload — so nothing downstream knows or cares whether an item came from
# ESPN's keyless news endpoint or one of the RSS feeds.
#
# News is deliberately *ephemeral* (CONTEXT.md "News ticker": "not part of a
# weekly snapshot"): a ``NewsFeed`` is the current 48-hour window, rebuilt every
# poll, cached to SQLite with ``fetched_at``, and never frozen into a
# ``WeeklySnapshot``.


class NewsBucket(StrEnum):
    """Why a news item matters to the Dead Parrots manager (spec issue #15;
    user story #38 — "labelled by bucket ... so I can tell at a glance why it
    matters").

    Ordered by precedence: a player who sits on more than one target list is
    tagged once, in the first bucket that claims them — a player on the Dead
    Parrots roster is "my roster" even if they also show up on the free-agent
    shortlist by mistake.
    """

    MY_ROSTER = "my_roster"
    OPPONENT = "opponent"
    FREE_AGENT = "free_agent"

    @property
    def precedence(self) -> int:
        return _BUCKET_PRECEDENCE[self]


_BUCKET_PRECEDENCE: dict[NewsBucket, int] = {
    NewsBucket.MY_ROSTER: 0,
    NewsBucket.OPPONENT: 1,
    NewsBucket.FREE_AGENT: 2,
}


@dataclass(frozen=True)
class PlayerTag:
    """One player a news item was matched to, and the bucket that match falls
    in. ``player_name`` is the canonical name from the target list (not the
    surface form in the article); ``matched_text`` is what actually matched in
    the title or summary, kept for provenance and UI highlighting.
    """

    player_name: str
    bucket: NewsBucket
    matched_text: str


@dataclass(frozen=True)
class NewsItem:
    """One retained, deduped, player-tagged news item.

    ``source`` is a ``+``-joined sorted label of every feed the item was seen in
    (e.g. ``"espn-api+espn-rss"``) — provenance for the data-freshness header,
    never branched on. ``published_at`` and ``fetched_at`` are tz-aware UTC.
    ``dedupe_key`` is the normalized-URL-or-title key the item was deduped on.
    """

    title: str
    url: str
    summary: str | None
    source: str
    published_at: datetime
    fetched_at: datetime
    tags: tuple[PlayerTag, ...]
    dedupe_key: str

    @property
    def buckets(self) -> tuple[NewsBucket, ...]:
        """The distinct buckets this item's tags fall in, in precedence order."""
        seen: list[NewsBucket] = []
        for tag in self.tags:
            if tag.bucket not in seen:
                seen.append(tag.bucket)
        return tuple(sorted(seen, key=lambda b: b.precedence))

    @property
    def tagged_players(self) -> tuple[str, ...]:
        return tuple(t.player_name for t in self.tags)


@dataclass(frozen=True)
class NewsFeed:
    """A whole 48-hour window of retained news items, newest first.

    Rebuilt every poll from the normalized items still inside ``window_hours`` of
    ``fetched_at``. ``fetched_at`` is the poll time stamped onto every item and
    onto the SQLite cache rows (spec issue #15: "cached to SQLite with
    ``fetched_at``").
    """

    fetched_at: datetime
    window_hours: int
    items: tuple[NewsItem, ...]

    def __len__(self) -> int:
        return len(self.items)

    def for_bucket(self, bucket: NewsBucket) -> tuple[NewsItem, ...]:
        return tuple(i for i in self.items if bucket in i.buckets)

    def for_player(self, player_name: str) -> tuple[NewsItem, ...]:
        want = player_name.casefold()
        return tuple(
            i for i in self.items if any(t.player_name.casefold() == want for t in i.tags)
        )
