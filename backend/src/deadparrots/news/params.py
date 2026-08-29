from __future__ import annotations

from dataclasses import dataclass

# The News module's tunable knobs (spec issue #15; CONTEXT.md "News ticker").
# None of these come from ``docs/methodology.md`` — news is not part of the
# projection model or a weekly snapshot — so every value here is a build choice
# pinned by ``test_news_params.py`` and overridable without a code change.


@dataclass(frozen=True)
class NewsParams:
    """Parameters for assembling a :class:`~deadparrots.news.models.NewsFeed`.

    ``window_hours`` is the retention window (spec: "keeps only the last 48
    hours"). ``min_poll_interval_minutes`` throttles the scheduled poll (spec:
    "at most every ~30 minutes"). ``future_skew_minutes`` tolerates a small
    clock difference between a feed's timestamps and ours before an item is
    treated as bogus and dropped.
    """

    window_hours: int = 48
    min_poll_interval_minutes: int = 30
    future_skew_minutes: int = 60

    def __post_init__(self) -> None:
        if self.window_hours <= 0:
            raise ValueError(f"window_hours must be positive: {self.window_hours!r}")
        if self.min_poll_interval_minutes < 0:
            raise ValueError(
                f"min_poll_interval_minutes must be non-negative: "
                f"{self.min_poll_interval_minutes!r}"
            )
        if self.future_skew_minutes < 0:
            raise ValueError(
                f"future_skew_minutes must be non-negative: {self.future_skew_minutes!r}"
            )


DEFAULT_NEWS_PARAMS = NewsParams()
