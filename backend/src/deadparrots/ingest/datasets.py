from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# The nflverse datasets the RIP TIDE model depends on (spec issue #1, ingestion
# section). Each maps a logical name to an ``nflreadpy`` loader plus the columns
# that must be present for the payload to be usable downstream. ``nflreadpy``'s
# modern ``load_player_stats`` already carries the individual-defender columns,
# so the IDP table is that same payload projected to its ``def_*`` columns
# rather than a separate download (see docs/adr/0004).


@dataclass(frozen=True)
class DatasetSpec:
    """One nflverse dataset: how to fetch it and what normalization requires."""

    name: str
    loader: str
    key_columns: tuple[str, ...]
    loader_kwargs: Mapping[str, object] = field(default_factory=dict)
    # When set, normalization keeps only the columns whose name starts with one
    # of these prefixes (key columns are always kept). Used to carve the IDP
    # table out of the wide weekly player-stats payload.
    projection_prefixes: tuple[str, ...] | None = None

    @property
    def source(self) -> str:
        """Stable ``pull_status`` source label, e.g. ``nflverse:pbp``."""
        return f"nflverse:{self.name}"


NFLVERSE_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec("pbp", "load_pbp", ("game_id", "play_id", "season", "week")),
    DatasetSpec(
        "player_stats",
        "load_player_stats",
        ("player_id", "season", "week"),
        {"summary_level": "week"},
    ),
    DatasetSpec("rosters", "load_rosters", ("season", "team")),
    DatasetSpec(
        "schedules",
        "load_schedules",
        ("game_id", "season", "week", "home_team", "away_team"),
    ),
    DatasetSpec("snap_counts", "load_snap_counts", ("game_id", "season", "week", "player", "team")),
    # nflverse reshaped depth charts for 2025+ (dated snapshots, ESPN-sourced);
    # these keys match the current format, not the pre-2025 season/week one.
    DatasetSpec("depth_charts", "load_depth_charts", ("dt", "team", "gsis_id", "pos_abb")),
    DatasetSpec("injuries", "load_injuries", ("season", "week", "team")),
    DatasetSpec(
        "idp",
        "load_player_stats",
        # Include a couple of the individual-defender columns as keys so a
        # player-stats payload that lost its defensive columns fails the pull
        # instead of silently caching an IDP table with no IDP stats.
        ("player_id", "season", "week", "def_tackles_solo", "def_pass_defended"),
        {"summary_level": "week"},
        projection_prefixes=(
            "player_",
            "position",
            "season",
            "week",
            "season_type",
            "game_id",
            "team",
            "opponent_team",
            "def_",
            "fumble_recovery_",
        ),
    ),
)

DATASETS_BY_NAME: dict[str, DatasetSpec] = {spec.name: spec for spec in NFLVERSE_DATASETS}
