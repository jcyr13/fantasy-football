from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ..consensus.models import ConsensusFeed
from ..lineup import RosterPlayer, role_of
from ..news import NewsTargets
from ..projection import (
    DEFAULT_PARAMS,
    PlayerHistory,
    ProjectionParams,
    UsageSnapshot,
    project,
)
from ..scoring import round_points
from ..simulation import seed_from_snapshot_id, sim_player_from_projection
from ..strategy import (
    ByePlayer,
    LeagueState,
    LeagueTeam,
    RemainingMatchup,
    TeamScoringForecast,
    TeamWeekScore,
)
from ..trade import (
    PlayerWeek,
    RivalRosterSpot,
    RivalTeam,
    TradeDeskState,
    TradePlayer,
)
from ..waiver import FreeAgent, RosteredPlayer, WaiverState
from ..yahoo.models import (
    FreeAgentListing,
    InjuryReport,
    MatchupSnapshot,
    RosterEntry,
    StandingsSnapshot,
)
from ._util import to_float
from .identity import PlayerResolver, normalize_name, normalize_team, slugify
from .inputs import AssembledPlayer, AssembledWeek
from .opportunity import player_games, target_week_opportunity, usage_by_player_week
from .scored_history import ScoredGame, scored_games_by_player, stat_rows_from_player_stats

# The thin real adapter (ADR-0013). Raw nflverse frames + normalized Yahoo
# objects in, one frozen ``AssembledWeek`` out. No I/O. Every place the v1 data
# is too thin for a layer's real input is approximated here and named in
# ``caveats`` — nothing thin reaches a screen unlabelled.

__all__ = ["assemble_week", "WEEKLY_FORECAST_SIGMA_FRACTION"]

REGULAR_SEASON_WEEKS = 14
PLAYOFF_TEAM_COUNT = 6

# Placeholder magnitudes, pinned by ``test_weekly_params.py`` (ADR-0013 §4), not
# calibrated — the same treatment ADR-0007 gives the sim's correlation shares.
# ``sigma`` for a team's season-rest weekly total, as a fraction of its mean.
WEEKLY_FORECAST_SIGMA_FRACTION = 0.18
# The mean a projection falls back to when a player has no scored history, no
# consensus number and no Yahoo projection to anchor on — enough to keep the
# lineup legal; the player is listed in ``AssembledWeek.caveats``.
NOMINAL_REPLACEMENT_POINTS = 1.0

_SEASON_ENDING = {
    "ir", "ir+", "injured reserve", "pup", "nfi", "suspended", "out for season",
    "season", "sus",
}
_OUT_THIS_WEEK = {"o", "out", "d", "doubtful"}


# --- schedule ---------------------------------------------------------------


def _schedule_index(
    schedule_rows: Iterable[Mapping[str, object]], season: int
) -> dict[str, dict[int, str]]:
    """``team abbr`` → ``{week: game_id}`` for one season."""
    index: dict[str, dict[int, str]] = {}
    for row in schedule_rows:
        if int(to_float(row.get("season"))) != season:
            continue
        week = int(to_float(row.get("week")))
        game_id = str(row.get("game_id") or "")
        for side in ("home_team", "away_team"):
            team = normalize_team(str(row.get(side) or "") or None)
            if team and week > 0:
                index.setdefault(team, {})[week] = game_id
    return index


def _bye_week_for(
    team: str | None, from_week: int, last_week: int, sched: Mapping[str, dict[int, str]]
) -> int | None:
    if not team or team not in sched:
        return None
    played = sched[team]
    # Only trust a "missing week" as a bye when the schedule actually covers
    # weeks past ``from_week`` for this team.
    if not any(w > from_week for w in played):
        return None
    for week in range(from_week, last_week + 1):
        if week not in played:
            return week
    return None


def _is_on_bye(team: str | None, week: int, sched: Mapping[str, dict[int, str]]) -> bool:
    """The team has no game in ``week`` and the schedule pull does cover that
    week for them (so a missing week is a real bye, not a short pull)."""
    return _bye_week_for(team, week, week, sched) == week


# --- availability ----------------------------------------------------------


def _availability(status: str | None) -> tuple[bool, bool]:
    """``(available_for_season, out_this_week)`` from a Yahoo injury string."""
    key = (status or "").strip().casefold()
    if not key:
        return True, False
    if key in _SEASON_ENDING or "injured reserve" in key or key.startswith("ir"):
        return False, False
    if key in _OUT_THIS_WEEK:
        return False, True
    return True, False


# --- one player ----------------------------------------------------------


@dataclass(frozen=True)
class _Resolved:
    assembled: AssembledPlayer
    scored: tuple[ScoredGame, ...]
    usage: Mapping[int, UsageSnapshot]
    birth_date: date | None
    used_nominal_mean: bool = False


def _resolve_player(
    *,
    name: str,
    yahoo_team: str | None,
    yahoo_position: str | None,
    yahoo_projected_points: float | None,
    injury_status: str | None,
    resolver: PlayerResolver,
    scored: Mapping[str, list[ScoredGame]],
    usage_all: Mapping[tuple[str, int], UsageSnapshot],
    sched: Mapping[str, dict[int, str]],
    season: int,
    week: int,
    rng_seed: int,
    consensus: ConsensusFeed | None,
    params: ProjectionParams,
) -> _Resolved:
    identity = resolver.resolve_or_synthetic(
        name, team=yahoo_team, position=yahoo_position
    )
    pid = identity.player_id
    role = role_of(yahoo_position or identity.position or "")
    nfl_team = identity.nfl_team or normalize_team(yahoo_team)

    games = scored.get(pid, [])
    p_usage = {w: u for (i, w), u in usage_all.items() if i == pid}
    history_games = player_games(
        games, season=season, half_life=params.decay_half_life_games, usage=p_usage
    )
    opportunity = target_week_opportunity(
        games, half_life=params.decay_half_life_games
    )

    consensus_points = _consensus_points(consensus, name)
    if consensus_points is None:
        consensus_points = yahoo_projected_points
    used_nominal = opportunity is None and consensus_points is None
    if used_nominal:
        consensus_points = NOMINAL_REPLACEMENT_POINTS

    history = PlayerHistory(player_id=pid, position=role, games=history_games)
    projection = project(
        history,
        opportunity,
        season=season,
        week=week,
        consensus_points=consensus_points,
        rng_seed=rng_seed,
        params=params,
    )

    game_id = sched.get(nfl_team or "", {}).get(week)
    sim = sim_player_from_projection(
        projection,
        nfl_team=nfl_team,
        game_id=game_id,
        residual_volume_floor=params.residual_volume_floor,
    )
    available, _out = _availability(injury_status)
    on_bye = _is_on_bye(nfl_team, week, sched)
    roster_player = RosterPlayer(
        player_id=pid,
        name=name,
        position=role,
        sim=sim,
        available=available and not on_bye,
    )
    return _Resolved(
        assembled=AssembledPlayer(
            player_id=pid,
            name=name,
            position=role,
            roster_player=roster_player,
            projection=projection,
            resolved=identity.resolved,
            yahoo_projected_points=yahoo_projected_points,
            nfl_team=nfl_team,
        ),
        scored=tuple(games),
        usage=p_usage,
        birth_date=identity.birth_date,
        used_nominal_mean=used_nominal,
    )


def _consensus_points(consensus: ConsensusFeed | None, name: str) -> float | None:
    if consensus is None:
        return None
    hit = consensus.get(name)
    if hit is not None:
        return hit.projection
    want = normalize_name(name)
    for proj in consensus.projections:
        if normalize_name(proj.player_name) == want:
            return proj.projection
    return None


# --- league / trade / waiver state --------------------------------------


def _slug(name: str) -> str:
    return slugify(name) or "team"


def _flat_weekly(points_for: float, completed_weeks: Sequence[int]) -> tuple[TeamWeekScore, ...]:
    if not completed_weeks:
        return ()
    per = points_for / len(completed_weeks)
    return tuple(TeamWeekScore(week=w, points_for=round_points(per)) for w in completed_weeks)


def _round_robin(
    team_ids: Sequence[str], weeks: Sequence[int]
) -> tuple[RemainingMatchup, ...]:
    """Circle-method round robin so every remaining week is a full slate over
    the 12 team ids (feeds only the playoff-odds season-rest sim)."""
    ids = list(team_ids)
    if len(ids) % 2:
        ids.append("__bye__")
    n = len(ids)
    rounds: list[list[tuple[str, str]]] = []
    order = ids[:]
    for _ in range(n - 1):
        pairs = [
            (order[i], order[n - 1 - i])
            for i in range(n // 2)
            if "__bye__" not in (order[i], order[n - 1 - i])
        ]
        rounds.append(pairs)
        order = [order[0], *order[-1:], *order[1:-1]]
    out: list[RemainingMatchup] = []
    for offset, week in enumerate(weeks):
        for a, b in rounds[offset % len(rounds)]:
            out.append(RemainingMatchup(week=week, team_id_a=a, team_id_b=b))
    return tuple(out)


def _league_state(
    *,
    standings: StandingsSnapshot,
    dp_team_name: str,
    dp_roster: Sequence[ByePlayer],
    season: int,
    week: int,
    prior_team_weeks: Mapping[str, Mapping[int, float]] | None,
) -> LeagueState:
    completed = list(range(1, week))
    remaining_weeks = list(range(week, REGULAR_SEASON_WEEKS + 1))
    teams: list[LeagueTeam] = []
    team_ids: list[str] = []
    for row in standings.rows:
        tid = _slug(row.team_name)
        team_ids.append(tid)
        is_dp = normalize_name(row.team_name) == normalize_name(dp_team_name)
        if prior_team_weeks and tid in prior_team_weeks:
            weekly = tuple(
                TeamWeekScore(week=w, points_for=p)
                for w, p in sorted(prior_team_weeks[tid].items())
            )
        else:
            weekly = _flat_weekly(row.points_for, completed)
        teams.append(
            LeagueTeam(
                team_id=tid,
                team_name=row.team_name,
                is_dead_parrots=is_dp,
                wins=row.wins,
                losses=row.losses,
                ties=row.ties,
                weekly_scores=weekly,
                division=row.division,
            )
        )
    forecasts = [
        TeamScoringForecast(
            team_id=t.team_id,
            mean=(m := (sum(s.points_for for s in t.weekly_scores) / len(t.weekly_scores))
                  if t.weekly_scores else 100.0),
            sigma=max(WEEKLY_FORECAST_SIGMA_FRACTION * m, 1.0),
        )
        for t in teams
    ]
    return LeagueState(
        season=season,
        current_week=week,
        teams=tuple(teams),
        remaining_schedule=_round_robin(team_ids, remaining_weeks),
        dead_parrots_roster=tuple(dp_roster),
        scoring_forecasts=tuple(forecasts),
        playoff_team_count=PLAYOFF_TEAM_COUNT,
        regular_season_weeks=REGULAR_SEASON_WEEKS,
    )


def _market_value(rr: _Resolved) -> float:
    yp = rr.assembled.yahoo_projected_points
    if yp is not None:
        return yp
    return rr.scored[-1].points if rr.scored else 0.0


def _history_pairs(
    scored: Sequence[ScoredGame], usage: Mapping[int, UsageSnapshot]
) -> tuple[PlayerWeek, ...]:
    return tuple(
        PlayerWeek(week=g.week, fantasy_points=g.points, usage=usage.get(g.week))
        for g in sorted(scored, key=lambda g: g.week)
    )


def _trade_state(
    *,
    resolved: Sequence[_Resolved],
    dp_ids: set[str],
    standings: StandingsSnapshot,
    dp_team_name: str,
    opponent_team_name: str,
    opponent_roster: Sequence[RosterEntry],
    resolver: PlayerResolver,
    season: int,
    week: int,
    as_of_date: date,
) -> TradeDeskState:
    weeks_remaining = max(REGULAR_SEASON_WEEKS - week + 1, 1)
    completed = list(range(1, week))

    # A best-effort market-value proxy: rank within role by the Yahoo weekly
    # projection (its trailing scored average when Yahoo has no number). The
    # model rank the trade edge is measured against comes from the layer itself.
    by_role: dict[str, list[_Resolved]] = {}
    for r in resolved:
        by_role.setdefault(r.assembled.position, []).append(r)
    market_rank: dict[str, int] = {}
    for group in by_role.values():
        ordered = sorted(group, key=_market_value, reverse=True)
        for rank, rr in enumerate(ordered, start=1):
            market_rank[rr.assembled.player_id] = rank

    players: list[TradePlayer] = []
    for r in resolved:
        a = r.assembled
        players.append(
            TradePlayer(
                player_id=a.player_id,
                name=a.name,
                position=a.position,
                history=_history_pairs(r.scored, r.usage),
                market_ros_rank=market_rank.get(a.player_id),
                model_ros_points=round_points(a.projection.projection * weeks_remaining),
                on_dead_parrots=a.player_id in dp_ids,
                injury_risk=0.0,
            )
        )

    opp_by_id: dict[str, RivalRosterSpot] = {}
    for entry in opponent_roster:
        identity = resolver.resolve_or_synthetic(
            entry.player_name, team=entry.nfl_team, position=entry.position
        )
        opp_by_id[identity.player_id] = RivalRosterSpot(
            player_id=identity.player_id,
            name=entry.player_name,
            position=entry.position or identity.position or "",
            birthdate=identity.birth_date,
        )

    rivals: list[RivalTeam] = []
    dp_points_for: tuple[float, ...] = ()
    for row in standings.rows:
        flat = _flat_weekly(row.points_for, completed)
        series = tuple(s.points_for for s in flat)
        if normalize_name(row.team_name) == normalize_name(dp_team_name):
            dp_points_for = series
            continue
        roster: tuple[RivalRosterSpot, ...] = ()
        if normalize_name(row.team_name) == normalize_name(opponent_team_name):
            roster = tuple(opp_by_id.values())
        rivals.append(
            RivalTeam(
                team_id=_slug(row.team_name),
                team_name=row.team_name,
                wins=row.wins,
                losses=row.losses,
                ties=row.ties,
                weekly_points_for=series,
                roster=roster,
            )
        )
    return TradeDeskState(
        season=season,
        current_week=week,
        as_of_date=as_of_date,
        players=tuple(players),
        rivals=tuple(rivals),
        dead_parrots_points_for=dp_points_for,
        regular_season_weeks=REGULAR_SEASON_WEEKS,
    )


def _waiver_state(
    *,
    fa_resolved: Sequence[_Resolved],
    dp_roster: Sequence[RosteredPlayer],
    standings: StandingsSnapshot,
    dp_team_name: str,
    season: int,
    week: int,
    as_of_date: date,
) -> WaiverState:
    weeks_remaining = max(REGULAR_SEASON_WEEKS - week + 1, 1)
    team_count = len(standings.rows) or 12
    priority = team_count // 2
    for row in standings.rows:
        if normalize_name(row.team_name) == normalize_name(dp_team_name):
            if row.waiver_priority is not None:
                priority = row.waiver_priority
            break
    priority = min(max(priority, 1), team_count)

    free_agents: list[FreeAgent] = []
    for r in fa_resolved:
        a = r.assembled
        free_agents.append(
            FreeAgent(
                player_id=a.player_id,
                name=a.name,
                position=a.position,
                ros_projected_points=round_points(a.projection.projection * weeks_remaining),
                next_week_ceiling=max(a.projection.ceiling, 0.0),
                bye_week=None,
            )
        )
    return WaiverState(
        season=season,
        current_week=week,
        as_of_date=as_of_date,
        free_agents=tuple(free_agents),
        dead_parrots_roster=tuple(dp_roster),
        waiver_priority=priority,
        team_count=team_count,
        regular_season_weeks=REGULAR_SEASON_WEEKS,
    )


# --- top level ---------------------------------------------------------


def assemble_week(
    *,
    matchup: MatchupSnapshot,
    free_agents: FreeAgentListing,
    injuries: InjuryReport,
    standings: StandingsSnapshot,
    player_stats_rows: Sequence[Mapping[str, object]],
    snap_rows: Sequence[Mapping[str, object]] = (),
    roster_rows: Sequence[Mapping[str, object]] = (),
    schedule_rows: Sequence[Mapping[str, object]] = (),
    consensus: ConsensusFeed | None = None,
    season: int,
    week: int,
    as_of_date: date,
    prior_team_weeks: Mapping[str, Mapping[int, float]] | None = None,
    projection_params: ProjectionParams = DEFAULT_PARAMS,
    free_agent_shortlist_size: int = 8,
) -> AssembledWeek:
    """Reconcile the week's pulls into one :class:`AssembledWeek` (ADR-0013)."""
    rng_seed = seed_from_snapshot_id(f"{season}-{week}")
    resolver = PlayerResolver(roster_rows)
    sched = _schedule_index(schedule_rows, season)

    stat_rows = stat_rows_from_player_stats(player_stats_rows)
    scored = scored_games_by_player(stat_rows)
    usage_all = usage_by_player_week(player_stats_rows, snap_rows, resolver)

    injuries_by_name = {
        normalize_name(e.player_name): e.status for e in injuries.entries
    }

    def _status_for(entry_status: str | None, name: str) -> str | None:
        return entry_status or injuries_by_name.get(normalize_name(name))

    def _resolve_entry(entry: RosterEntry) -> _Resolved:
        return _resolve_player(
            name=entry.player_name,
            yahoo_team=entry.nfl_team,
            yahoo_position=entry.position,
            yahoo_projected_points=entry.yahoo_projected_points,
            injury_status=_status_for(entry.injury_status, entry.player_name),
            resolver=resolver,
            scored=scored,
            usage_all=usage_all,
            sched=sched,
            season=season,
            week=week,
            rng_seed=rng_seed,
            consensus=consensus,
            params=projection_params,
        )

    dp_entries = [e for e in matchup.dead_parrots.entries if e.slot.upper() not in {"IR", "IR+"}]
    opp_entries = [e for e in matchup.opponent.entries if e.slot.upper() not in {"IR", "IR+"}]

    dp_resolved = [_resolve_entry(e) for e in dp_entries]
    opp_resolved = [_resolve_entry(e) for e in opp_entries]

    fa_resolved = [
        _resolve_player(
            name=f.player_name,
            yahoo_team=f.nfl_team,
            yahoo_position=f.position,
            yahoo_projected_points=f.yahoo_projected_points,
            injury_status=_status_for(f.injury_status, f.player_name),
            resolver=resolver,
            scored=scored,
            usage_all=usage_all,
            sched=sched,
            season=season,
            week=week,
            rng_seed=rng_seed,
            consensus=consensus,
            params=projection_params,
        )
        for f in free_agents.players
    ]

    dp_ids = {r.assembled.player_id for r in dp_resolved}

    dp_yahoo_starters = tuple(
        r.assembled.player_id
        for e, r in zip(dp_entries, dp_resolved)
        if e.is_starter
    )
    opp_yahoo_starters = tuple(
        r.assembled.player_id
        for e, r in zip(opp_entries, opp_resolved)
        if e.is_starter
    )

    # Dead Parrots roster for the bye-crunch map / waiver need detection.
    dp_bye_players: list[ByePlayer] = []
    dp_rostered: list[RosteredPlayer] = []
    for e, r in zip(dp_entries, dp_resolved):
        avail, out_now = _availability(_status_for(e.injury_status, e.player_name))
        bye = _bye_week_for(r.assembled.nfl_team, week, REGULAR_SEASON_WEEKS, sched)
        dp_bye_players.append(
            ByePlayer(
                player_id=r.assembled.player_id,
                name=e.player_name,
                position=r.assembled.position,
                bye_week=bye,
                is_starter=e.is_starter,
                available=avail,
            )
        )
        dp_rostered.append(
            RosteredPlayer(
                player_id=r.assembled.player_id,
                name=e.player_name,
                position=r.assembled.position,
                bye_week=bye,
                is_starter=e.is_starter,
                available=avail,
                out_this_week=out_now,
            )
        )

    league_state = _league_state(
        standings=standings,
        dp_team_name=matchup.dead_parrots.team_name,
        dp_roster=dp_bye_players,
        season=season,
        week=week,
        prior_team_weeks=prior_team_weeks,
    )
    trade_state = _trade_state(
        resolved=[*dp_resolved, *opp_resolved],
        dp_ids=dp_ids,
        standings=standings,
        dp_team_name=matchup.dead_parrots.team_name,
        opponent_team_name=matchup.opponent.team_name,
        opponent_roster=opp_entries,
        resolver=resolver,
        season=season,
        week=week,
        as_of_date=as_of_date,
    )
    waiver_state = _waiver_state(
        fa_resolved=fa_resolved,
        dp_roster=dp_rostered,
        standings=standings,
        dp_team_name=matchup.dead_parrots.team_name,
        season=season,
        week=week,
        as_of_date=as_of_date,
    )

    fa_sorted = sorted(
        fa_resolved, key=lambda r: r.assembled.projection.projection, reverse=True
    )
    shortlist = tuple(r.assembled.name for r in fa_sorted[:free_agent_shortlist_size])
    news_targets = NewsTargets(
        my_roster=tuple(e.player_name for e in matchup.dead_parrots.entries),
        opponent=tuple(e.player_name for e in matchup.opponent.entries),
        free_agents=shortlist,
    )

    caveats = _caveats(
        dp_resolved=dp_resolved,
        opp_resolved=opp_resolved,
        fa_resolved=fa_resolved,
        prior_team_weeks=prior_team_weeks,
        consensus_wired=consensus is not None,
        sched=sched,
        dp_bye_players=dp_bye_players,
    )

    return AssembledWeek(
        season=season,
        week=week,
        as_of_date=as_of_date,
        rng_seed=rng_seed,
        dead_parrots_team_name=matchup.dead_parrots.team_name,
        opponent_team_name=matchup.opponent.team_name,
        opponent_assumption_hint="yahoo-set",
        dead_parrots=tuple(r.assembled for r in dp_resolved),
        opponent=tuple(r.assembled for r in opp_resolved),
        free_agents=tuple(r.assembled for r in fa_resolved),
        dead_parrots_yahoo_starters=dp_yahoo_starters,
        opponent_yahoo_starters=opp_yahoo_starters,
        opponent_prior_starters=None,
        dead_parrots_yahoo_projected_total=matchup.dead_parrots.yahoo_projected_total,
        opponent_yahoo_projected_total=matchup.opponent.yahoo_projected_total,
        league_state=league_state,
        trade_state=trade_state,
        waiver_state=waiver_state,
        news_targets=news_targets,
        caveats=caveats,
    )


def _caveats(
    *,
    dp_resolved: Sequence[_Resolved],
    opp_resolved: Sequence[_Resolved],
    fa_resolved: Sequence[_Resolved],
    prior_team_weeks: Mapping[str, Mapping[int, float]] | None,
    consensus_wired: bool,
    sched: Mapping[str, dict[int, str]],
    dp_bye_players: Sequence[ByePlayer],
) -> tuple[str, ...]:
    everyone = (*dp_resolved, *opp_resolved, *fa_resolved)
    out: list[str] = [
        "Projection means use a decay-weighted trailing average of scored "
        "actuals as the opportunity baseline, not a usage forecast "
        "(ADR-0013 §3).",
    ]
    unresolved = sorted({r.assembled.name for r in everyone if not r.assembled.resolved})
    if unresolved:
        out.append(
            "No nflverse match for: "
            + ", ".join(unresolved)
            + " — projection falls back to the Yahoo number."
        )
    nominal = sorted({r.assembled.name for r in everyone if r.used_nominal_mean})
    if nominal:
        out.append(
            "No history, consensus or Yahoo number for: "
            + ", ".join(nominal)
            + f" — projected at a nominal {NOMINAL_REPLACEMENT_POINTS:.0f}-point "
            "replacement level."
        )
    if not consensus_wired:
        out.append(
            "No consensus feed was supplied — projections have no external "
            "cross-check and thin-history players lean on the Yahoo number."
        )
    if not prior_team_weeks:
        out.append(
            "No real per-week team history yet (issue #17): team strength is a "
            "percentile over an even split of each team's season points-for, and "
            "the remaining schedule is a synthetic round robin. Expected wins, "
            "luck and playoff odds are computed on that flat split and are not "
            "reliable in v1 (ADR-0013 §4)."
        )
    if not any(p.bye_week is not None for p in dp_bye_players):
        out.append(
            "No future NFL byes in the schedule pull — the bye-crunch map "
            "cannot see upcoming byes."
        )
    out.append(
        "The desperate-team read has full rosters only for the current "
        "opponent; other rivals score on record and points-for alone."
    )
    return tuple(out)
