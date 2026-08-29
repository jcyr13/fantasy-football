from __future__ import annotations

import logging

from ..config import Settings
from ..yahoo.models import MatchupSnapshot
from ..yahoo.normalize import YahooNormalizationError, normalize_matchup
from ..yahoo.pages import YahooPage
from ..yahoo.raw import YahooRawStore
from .tagging import NewsTargets

logger = logging.getLogger(__name__)

# Resolving the news poll's target lists from what the app already has on disk.
# The Dead Parrots and current-opponent rosters come straight from the most
# recent Yahoo assisted pull's matchup page; the free-agent shortlist is left
# empty until the assembled weekly view (issue #16) computes it — it is a ranked
# subset, not a raw page, and belongs with the layer that ranks free agents.


def targets_from_latest_yahoo_pull(raw_store: YahooRawStore) -> NewsTargets:
    """``NewsTargets`` built from the newest archived Yahoo matchup payload, or
    an empty one when there is no usable pull yet (the poll then archives feeds
    and records status but retains nothing — the same graceful-degradation the
    app starts in).
    """
    pull_ids = raw_store.pull_ids()
    for pull_id in reversed(pull_ids):
        payload = raw_store.load_payload(pull_id, YahooPage.MATCHUP)
        if payload is None:
            continue
        try:
            matchup = normalize_matchup(payload)
        except YahooNormalizationError as exc:
            logger.warning("news targets: matchup pull %s unusable (%s)", pull_id, exc)
            continue
        return _targets_from_matchup(matchup)
    return NewsTargets.empty()


def _targets_from_matchup(matchup: MatchupSnapshot) -> NewsTargets:
    return NewsTargets(
        my_roster=tuple(e.player_name for e in matchup.dead_parrots.entries),
        opponent=tuple(e.player_name for e in matchup.opponent.entries),
    )


def build_yahoo_targets_provider(settings: Settings):
    """A zero-arg provider the scheduled poll calls each fire to pick up the
    latest roster without a restart.
    """
    raw_store = YahooRawStore(settings.data_dir)

    def _provider() -> NewsTargets:
        return targets_from_latest_yahoo_pull(raw_store)

    return _provider
