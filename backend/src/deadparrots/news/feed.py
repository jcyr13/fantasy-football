from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from .models import NewsFeed, NewsItem
from .normalize import ParsedArticle
from .params import DEFAULT_NEWS_PARAMS, NewsParams
from .tagging import NewsTargets, compile_targets, tag_text

# Assembling a ``NewsFeed`` from normalized articles (spec issue #15). Pure and
# deterministic — parsed articles + the target lists + ``now`` in, a
# ``NewsFeed`` out. This is the seam the recorded-payload test drives end to end
# alongside ``normalize_payload``.
#
# Order of operations (spec issue #15, acceptance criteria):
#   1. drop anything outside the last ``window_hours`` (or bogusly future-dated)
#   2. dedupe by normalized URL, falling back to normalized title
#   3. tag each survivor to players / buckets; drop items that tag nothing
#   4. sort newest first


def build_news_feed(
    articles: Sequence[ParsedArticle],
    targets: NewsTargets,
    *,
    now: datetime,
    fetched_at: datetime | None = None,
    params: NewsParams = DEFAULT_NEWS_PARAMS,
) -> NewsFeed:
    """Turn normalized articles into the current retained, deduped, tagged feed.

    ``now`` anchors the 48-hour window; ``fetched_at`` (defaulting to ``now``)
    is the poll timestamp stamped onto every item. An all-empty ``targets``
    yields an empty feed — news is only kept when it is relevant (user story
    #37).
    """
    stamp = fetched_at or now
    cutoff = now - timedelta(hours=params.window_hours)
    horizon = now + timedelta(minutes=params.future_skew_minutes)

    fresh = [a for a in articles if cutoff <= a.published_at <= horizon]
    deduped = _dedupe(fresh)

    compiled = compile_targets(targets)
    items: list[NewsItem] = []
    for key, group in deduped:
        primary = group[0]
        tags = tag_text(primary.title, primary.summary, compiled)
        if not tags:
            continue
        items.append(
            NewsItem(
                title=primary.title,
                url=primary.url,
                summary=next((a.summary for a in group if a.summary), None),
                source="+".join(sorted({a.source for a in group})),
                published_at=min(a.published_at for a in group),
                fetched_at=stamp,
                tags=tags,
                dedupe_key=key,
            )
        )

    items.sort(key=lambda i: (i.published_at, i.title.casefold()), reverse=True)
    return NewsFeed(fetched_at=stamp, window_hours=params.window_hours, items=tuple(items))


# --- dedupe -----------------------------------------------------------------


def _dedupe(articles: Sequence[ParsedArticle]) -> list[tuple[str, list[ParsedArticle]]]:
    """Group articles by dedupe key, preserving first-seen order of the groups.

    An article's key is its normalized URL, or its normalized title when it has
    no usable URL. Two feeds carrying the same story (same link, or the same
    headline with tracking-only URL differences) collapse to one group.
    """
    order: list[str] = []
    groups: dict[str, list[ParsedArticle]] = {}
    for article in articles:
        key = _dedupe_key(article)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(article)
    return [(key, groups[key]) for key in order]


def _dedupe_key(article: ParsedArticle) -> str:
    url_key = _normalize_url(article.url)
    if url_key:
        return f"url:{url_key}"
    return f"title:{_normalize_title(article.title)}"


def _normalize_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.casefold()
    if not parts.netloc:
        return text.casefold()
    host = parts.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    # Scheme, query, and fragment are dropped: feeds differ on http/https and
    # append per-feed tracking params to the same canonical article.
    return urlunsplit(("", host, path, "", ""))


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").casefold()).strip()
