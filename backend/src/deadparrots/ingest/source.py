from __future__ import annotations

import logging

import polars as pl

from .datasets import DatasetSpec
from .runner import NflverseSource

logger = logging.getLogger(__name__)


class LiveNflverseSource(NflverseSource):
    """Fetches datasets from nflverse via ``nflreadpy``.

    This is the real network boundary and is deliberately kept trivial: it maps
    a spec's ``loader`` name to the ``nflreadpy`` function and forwards the
    configured seasons plus any loader kwargs. Not covered by unit tests.
    """

    def __init__(self, seasons: list[int] | None = None) -> None:
        # ``None`` -> just the current season, resolved per pull; a list pins it.
        self._seasons = seasons

    def load(self, spec: DatasetSpec) -> pl.DataFrame:
        import nflreadpy as nfl

        loader = getattr(nfl, spec.loader)
        seasons = self._seasons or [nfl.get_current_season()]
        logger.info("nflreadpy.%s(seasons=%s, %s)", spec.loader, seasons, dict(spec.loader_kwargs))
        return loader(seasons, **dict(spec.loader_kwargs))
