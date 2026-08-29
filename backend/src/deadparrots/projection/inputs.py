from __future__ import annotations

from dataclasses import dataclass

# The projection model's input vocabulary. ``project`` consumes these domain
# objects and nothing else — it has no knowledge of nflverse column names, the
# consensus feed's payload shape, or any I/O. Whoever assembles a weekly league
# state is responsible for turning raw pulls into these.
#
# Signature summarised in issue #9:
#   (player_history, opportunity_metrics, consensus_feed, params, rng_seed)
#     -> weekly point distribution  (floor P10 / projection P50 / ceiling P90)
#
# ``consensus_feed`` is passed to ``project`` as a single resolved number
# (``consensus_points``) — the caller looks the player up in the feed — so this
# module never imports the consensus package.


@dataclass(frozen=True)
class UsageSnapshot:
    """The four opportunity signals for one game (methodology §3.4).

    ``snap_share``, ``target_share`` and ``route_participation`` are shares in
    ``[0, 1]``. ``red_zone_share`` is the player's share of the team's red-zone
    opportunities that game, also in ``[0, 1]`` (the caller normalises raw
    red-zone touch counts).
    """

    snap_share: float
    target_share: float
    route_participation: float
    red_zone_share: float


@dataclass(frozen=True)
class PlayerGame:
    """One historical scored game for a player.

    ``actual_points`` is the RIP TIDE total the (validated) scoring engine
    assigned that week. ``expected_points`` is the opportunity model's ex-ante
    mean for that same game — ``actual - expected`` is the residual the shape
    model learns from (§3.2 step 2). ``usage`` may be ``None`` for a game whose
    snap/route data never landed; such games still count toward the history but
    are skipped by the usage-trend slope.
    """

    season: int
    week: int
    actual_points: float
    expected_points: float
    usage: UsageSnapshot | None = None


@dataclass(frozen=True)
class PlayerHistory:
    """A player's scored history plus the two role-status flags (§3.7).

    ``games`` may be in any order — :func:`project` sorts by ``(season, week)``.
    ``is_rookie`` and ``role_change`` force the consensus fallback and the
    low-confidence flag regardless of how many games are present.
    """

    player_id: str
    position: str
    games: tuple[PlayerGame, ...]
    is_rookie: bool = False
    role_change: bool = False


@dataclass(frozen=True)
class OpportunityMetrics:
    """The opportunity model's forecast for the target week (§3.2 step 1).

    ``expected_points`` is the role-based mean — expected usage translated into
    expected RIP TIDE points — *before* the trend and matchup adjustments this
    module applies. ``projected_usage`` is carried for provenance / UI only;
    the trend adjustment is derived from history, not from this snapshot.
    """

    expected_points: float
    projected_usage: UsageSnapshot | None = None


@dataclass(frozen=True)
class MatchupContext:
    """Inputs to the capped matchup adjustment (§3.5).

    Both figures are RIP TIDE fantasy points the scoring engine computed over
    play-by-play, decay-weighted with the same half-life: what this week's
    opponent defense has allowed to the player's position, and the league
    average of that same quantity. The raw factor is their ratio.
    """

    opponent_points_allowed_to_position: float
    league_average_points_allowed_to_position: float
