from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from ..projection import OpportunityMetrics, PlayerGame, UsageSnapshot, decay_weights
from .identity import PlayerResolver, normalize_name, normalize_team
from .scored_history import ScoredGame

# The projection model (#9) consumes a per-game "expected points" baseline and a
# target-week ``OpportunityMetrics`` from an opportunity model that no ticket has
# built. v1's stand-in (ADR-0013 §3): a **decay-weighted trailing mean of the
# player's own scored actuals**, same half-life as the projection shape decay.
# ``actual − expected`` is then real week-to-week variation around recent form,
# which keeps ``project`` on its PLAYER_HISTORY shape path. The usage snapshot is
# filled from ``snap_counts`` + ``player_stats`` where present, ``None``
# otherwise.

__all__ = [
    "player_games",
    "target_week_opportunity",
    "usage_by_player_week",
]


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _decay_weighted_mean(values: Sequence[float], half_life: float) -> float:
    """Decay-weighted mean, newest value weighted highest. ``[]`` → ``0.0``."""
    if not values:
        return 0.0
    weights = decay_weights(len(values), half_life)
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def usage_by_player_week(
    player_stats_rows: Iterable[Mapping[str, object]],
    snap_rows: Iterable[Mapping[str, object]],
    resolver: PlayerResolver,
) -> dict[tuple[str, int], UsageSnapshot]:
    """``(player_id, week)`` → :class:`UsageSnapshot`.

    ``snap_share`` / ``route_participation`` come from ``snap_counts``'
    ``offense_pct`` (routes are not in the v1 pulls, so route participation is
    approximated by snap share). ``target_share`` is the player's targets over
    the team's targets that week. ``red_zone_share`` is 0.0 — not in the v1
    pulls — which contributes a flat (zero-slope) series to the usage trend.
    """
    team_targets: dict[tuple[str, int], float] = {}
    for row in player_stats_rows:
        team = normalize_team(str(row.get("team") or row.get("recent_team") or "") or None)
        week = int(_num(row.get("week")))
        if team and week > 0:
            team_targets[(team, week)] = team_targets.get((team, week), 0.0) + _num(
                row.get("targets")
            )

    snap_pct: dict[tuple[str, str, int], float] = {}
    for row in snap_rows:
        name = normalize_name(str(row.get("player") or row.get("player_name") or ""))
        team = normalize_team(str(row.get("team") or "") or None)
        week = int(_num(row.get("week")))
        if name and team and week > 0:
            snap_pct[(name, team, week)] = _num(row.get("offense_pct"))

    out: dict[tuple[str, int], UsageSnapshot] = {}
    for row in player_stats_rows:
        raw_id = str(row.get("player_id") or row.get("gsis_id") or "").strip()
        if not raw_id:
            continue
        name = str(row.get("player_display_name") or row.get("player_name") or "")
        team = normalize_team(str(row.get("team") or row.get("recent_team") or "") or None)
        week = int(_num(row.get("week")))
        if week <= 0:
            continue
        resolved = resolver.resolve(name, team=team, position=str(row.get("position") or ""))
        pid = resolved.player_id if resolved is not None else raw_id
        snap = snap_pct.get((normalize_name(name), team or "", week))
        tt = team_targets.get((team or "", week), 0.0)
        targets = _num(row.get("targets"))
        target_share = (targets / tt) if tt > 0 else 0.0
        if snap is None and target_share == 0.0:
            continue
        snap_share = snap if snap is not None else 0.0
        out[(pid, week)] = UsageSnapshot(
            snap_share=min(max(snap_share, 0.0), 1.0),
            target_share=min(max(target_share, 0.0), 1.0),
            route_participation=min(max(snap_share, 0.0), 1.0),
            red_zone_share=0.0,
        )
    return out


def player_games(
    scored: Sequence[ScoredGame],
    *,
    season: int,
    half_life: float,
    usage: Mapping[int, UsageSnapshot] | None = None,
) -> tuple[PlayerGame, ...]:
    """Turn a resolved player's scored weeks into ``PlayerGame``s.

    Each game's ``expected_points`` is the decay-weighted mean of the *earlier*
    weeks' actuals (the player's recent form going into that week); the first
    game has no prior, so expected equals actual and its residual is zero.
    """
    usage = usage or {}
    out: list[PlayerGame] = []
    prior: list[float] = []
    for game in sorted(scored, key=lambda g: g.week):
        expected = _decay_weighted_mean(prior, half_life) if prior else game.points
        out.append(
            PlayerGame(
                season=season,
                week=game.week,
                actual_points=game.points,
                expected_points=expected,
                usage=usage.get(game.week),
            )
        )
        prior.append(game.points)
    return tuple(out)


def target_week_opportunity(
    scored: Sequence[ScoredGame],
    *,
    half_life: float,
) -> OpportunityMetrics | None:
    """The target-week opportunity mean: the decay-weighted mean of every
    completed week's actual. ``None`` when the player has no scored history —
    the caller then falls back to the Yahoo projection."""
    points = [g.points for g in sorted(scored, key=lambda g: g.week)]
    if not points:
        return None
    return OpportunityMetrics(expected_points=_decay_weighted_mean(points, half_life))
