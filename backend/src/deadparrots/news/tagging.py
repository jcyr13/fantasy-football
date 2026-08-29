from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field

from .models import NewsBucket, PlayerTag

# Name-matching a news article to players (spec issue #15: "tags each item to
# players by name-matching against the Dead Parrots roster, the current
# opponent's roster, and a free-agent shortlist"). Pure — a title + summary and
# the three target lists in, a tuple of ``PlayerTag`` out.
#
# The target lists are an *input*, not something this module computes: whoever
# assembles the weekly view (issue #16) turns the latest Yahoo pull's rosters
# and the free-agent shortlist into a ``NewsTargets``. Here it plays the role
# ``WaiverState`` plays for the waiver layer — a sibling input shape, resolved
# upstream (ADR-0011, ADR-0012).

# Name suffixes that a feed may print or drop freely; stripped from both the
# target name and the article text before matching so "Odell Beckham Jr." in a
# headline still matches a roster entry of "Odell Beckham".
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


@dataclass(frozen=True)
class NewsTargets:
    """The three name lists a news item is matched against, in bucket-precedence
    order. Any list may be empty; an all-empty ``NewsTargets`` tags nothing
    (every item is then dropped by ``build_news_feed``).
    """

    my_roster: tuple[str, ...] = ()
    opponent: tuple[str, ...] = ()
    free_agents: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> NewsTargets:
        return cls()

    def is_empty(self) -> bool:
        return not (self.my_roster or self.opponent or self.free_agents)

    def entries(self) -> Iterator[tuple[str, NewsBucket]]:
        """``(canonical_name, bucket)`` for every target, my-roster first so a
        player on two lists is claimed by the higher-precedence bucket.
        """
        for name in self.my_roster:
            yield name, NewsBucket.MY_ROSTER
        for name in self.opponent:
            yield name, NewsBucket.OPPONENT
        for name in self.free_agents:
            yield name, NewsBucket.FREE_AGENT


@dataclass(frozen=True)
class _CompiledTarget:
    canonical_name: str
    bucket: NewsBucket
    pattern: re.Pattern[str]
    normalized: str = field(compare=False)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _normalize(text: str) -> str:
    """Casefold, drop accents, turn every run of non-alphanumerics into a single
    space, and strip trailing name suffixes. ``"A.J. Brown"`` and
    ``"AJ  Brown"`` both normalize to ``"aj brown"``.
    """
    folded = _strip_accents(str(text)).casefold()
    tokens = [t for t in re.split(r"[^a-z0-9]+", folded) if t]
    while len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _compile_target(name: str, bucket: NewsBucket) -> _CompiledTarget | None:
    normalized = _normalize(name)
    if not normalized:
        return None
    # Word-boundary match on the normalized haystack; internal whitespace in the
    # name is allowed to be any single space (the haystack is already collapsed).
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])")
    return _CompiledTarget(name, bucket, pattern, normalized)


def compile_targets(targets: NewsTargets) -> tuple[_CompiledTarget, ...]:
    """One compiled matcher per target, de-duplicated by canonical name so a
    player on two lists is matched only in their highest-precedence bucket.
    """
    compiled: list[_CompiledTarget] = []
    seen: set[str] = set()
    for name, bucket in targets.entries():
        key = _normalize(name)
        if not key or key in seen:
            continue
        target = _compile_target(name, bucket)
        if target is None:
            continue
        seen.add(key)
        compiled.append(target)
    return tuple(compiled)


def tag_text(
    title: str,
    summary: str | None,
    targets: NewsTargets | tuple[_CompiledTarget, ...],
) -> tuple[PlayerTag, ...]:
    """Every target whose name appears in ``title`` or ``summary``, as a
    ``PlayerTag`` in bucket-precedence then name order.

    ``targets`` may be a :class:`NewsTargets` or the output of
    ``compile_targets`` — pass the compiled form when tagging many articles
    against the same lists.
    """
    compiled = (
        targets if isinstance(targets, tuple) else compile_targets(targets)
    )
    haystack = _normalize(f"{title} {summary or ''}")
    if not haystack:
        return ()

    tags: list[PlayerTag] = []
    for target in compiled:
        if target.pattern.search(haystack):
            tags.append(
                PlayerTag(
                    player_name=target.canonical_name,
                    bucket=target.bucket,
                    matched_text=target.normalized,
                )
            )
    tags.sort(key=lambda t: (t.bucket.precedence, t.player_name.casefold()))
    return tuple(tags)
