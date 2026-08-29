from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ..scoring import ScoringUnit

# The normalized consensus-feed domain objects (spec issue #8; CONTEXT.md
# "Consensus feed"). Everything downstream of the source interface consumes
# these and never sees a raw payload — so nothing downstream knows or cares
# whether the projections came from ``ffanalytics`` in the R sidecar or the
# Sleeper public API Week-1 stopgap (docs/adr/0005).
#
# A ``ConsensusProjection`` is a single scored *mean* — "the consensus number"
# shown next to the model's own number and Yahoo's, and the fallback projection
# for thin-history players (docs/methodology.md §2). It is deliberately NOT a
# distribution: the model supplies floor / projection / ceiling from positional
# residuals (methodology §3.1–§3.7), and the consensus feed must not be mistaken
# for that shape.


@dataclass(frozen=True)
class ConsensusProjection:
    """One player's weekly consensus projection, re-scored to RIP TIDE rules by
    the scoring engine.

    ``projection`` is the RIP TIDE points the engine assigns to the consensus
    mean stat line (``scored_stats``). ``source_points`` is the source's own
    (non-RIP-TIDE) points total, kept for provenance and never read downstream.
    """

    entity_id: str
    player_name: str
    nfl_team: str | None
    position: str
    season: int
    week: int
    unit: ScoringUnit
    projection: float
    scored_stats: Mapping[str, float]
    source_points: float | None = None
    gsis_id: str | None = None
    sleeper_id: str | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.entity_id, self.season, self.week)


@dataclass(frozen=True)
class ConsensusFeed:
    """A whole week's consensus projections from one source.

    ``source`` is the implementation label (``ffanalytics`` or ``sleeper``) —
    retained for the data-freshness header and provenance, never branched on by
    the projection model.
    """

    source: str
    season: int
    week: int
    generated_at: datetime
    projections: tuple[ConsensusProjection, ...]

    def __len__(self) -> int:
        return len(self.projections)

    def by_entity_id(self) -> dict[str, ConsensusProjection]:
        return {p.entity_id: p for p in self.projections}

    def for_unit(self, unit: ScoringUnit) -> tuple[ConsensusProjection, ...]:
        return tuple(p for p in self.projections if p.unit is unit)

    def for_position(self, position: str) -> tuple[ConsensusProjection, ...]:
        want = position.upper()
        return tuple(p for p in self.projections if p.position.upper() == want)

    def get(self, player_name: str) -> ConsensusProjection | None:
        """The first projection whose player name matches (case-insensitive)."""
        want = player_name.casefold()
        return next(
            (p for p in self.projections if p.player_name.casefold() == want), None
        )
