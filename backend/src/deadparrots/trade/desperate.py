from __future__ import annotations

from dataclasses import dataclass

from ..projection import decay_weights, weighted_mean
from .inputs import RivalTeam, TradeDeskState
from .params import DEFAULT_TRADE_PARAMS, TradeParams

# The desperate-team read (methodology §4.9): rank the other 11 managers by a
# composite willingness-to-deal score from four equally-weighted components —
#
#   1. sub-.500 record        how far below .500 the record sits
#   2. low points-for pct     §4.1's decay-weighted points-for, as a percentile
#                             against the full 12-team league, inverted
#   3. roster age             mean age of rostered players (nflverse birthdates)
#   4. own bye-week crunch     rostered players with a bye still ahead (§4.4,
#                             simplified — a rival's starter flags are not in
#                             the pull, so this counts roster-wide byes rather
#                             than grading a lineup)
#
# Each raw component is min-max normalized to [0, 1] across the 11 rivals (an
# all-equal component contributes 0); a team with no roster birthdates scores a
# neutral 0.5 on the age component rather than being floored to the youngest
# end. The weighted sum is the composite, and the top ``desperate_surface_count``
# are surfaced with the components that flagged them. Component weights are equal
# and a review item (§5 row 12 / §6 Q5). See ADR-0010.

__all__ = [
    "DesperateComponent",
    "DesperateTeam",
    "DesperateTeamRead",
    "desperate_team_read",
]

_RECORD = "record"
_POINTS_FOR = "points_for"
_ROSTER_AGE = "roster_age"
_BYE_CRUNCH = "bye_crunch"


@dataclass(frozen=True)
class DesperateComponent:
    """One of the four willingness-to-deal signals for one rival."""

    name: str
    raw: float
    normalized: float
    weight: float
    detail: str


@dataclass(frozen=True)
class DesperateTeam:
    """One rival's composite willingness-to-deal score and its parts."""

    team_id: str
    team_name: str
    score: float
    rank: int  # 1 = most desperate
    components: tuple[DesperateComponent, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DesperateTeamRead:
    """The desperate-team read for the whole league."""

    ranked: tuple[DesperateTeam, ...]
    surfaced: tuple[DesperateTeam, ...]


def _decay_weighted_points_for(series: list[float], half_life_weeks: float) -> float:
    if not series:
        return 0.0
    return weighted_mean(series, decay_weights(len(series), half_life_weeks))


def _percentile_rank(value: float, population: list[float]) -> float:
    """Percentile rank of ``value`` within ``population`` (0–100), a tie
    counting half. ``population`` includes ``value`` itself."""
    if len(population) <= 1:
        return 50.0
    below = sum(1 for o in population if o < value)
    equal = sum(1 for o in population if o == value) - 1  # exclude self
    return 100.0 * (below + 0.5 * max(equal, 0)) / (len(population) - 1)


def _mean_roster_age(team: RivalTeam, state: TradeDeskState) -> float | None:
    ages = [
        (state.as_of_date - spot.birthdate).days / 365.25
        for spot in team.roster
        if spot.birthdate is not None
    ]
    if not ages:
        return None
    return sum(ages) / len(ages)


def _bye_crunch_count(team: RivalTeam, state: TradeDeskState) -> int:
    upcoming = set(state.upcoming_weeks())
    return sum(1 for spot in team.roster if spot.bye_week in upcoming)


def _normalize(raw: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a ``team_id -> raw`` map to [0, 1]; all-equal ⇒ 0."""
    values = list(raw.values())
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi - lo <= 1e-12:
        return {tid: 0.0 for tid in raw}
    return {tid: (v - lo) / (hi - lo) for tid, v in raw.items()}


def _normalize_ages(age_by_team: dict[str, float | None]) -> dict[str, float]:
    """Min-max normalize mean roster age over the teams that have birthdate
    data; a team with none scores a **neutral 0.5** rather than being floored
    to the youngest end of the scale."""
    with_data = {tid: age for tid, age in age_by_team.items() if age is not None}
    normalized = _normalize(with_data)
    return {tid: normalized.get(tid, 0.5) for tid in age_by_team}


def _reasons_for(
    components: tuple[DesperateComponent, ...], params: TradeParams
) -> tuple[str, ...]:
    flagged = sorted(
        (c for c in components if c.normalized >= params.desperate_reason_threshold),
        key=lambda c: -c.normalized,
    )
    return tuple(c.detail for c in flagged) or (
        "no single component stands out — ranked on the composite",
    )


def _components_for(
    team: RivalTeam,
    *,
    raw_record: float,
    raw_pf: float,
    pct: float,
    age: float | None,
    raw_bye: float,
    norm: dict[str, float],
    params: TradeParams,
) -> tuple[DesperateComponent, ...]:
    return (
        DesperateComponent(
            name=_RECORD,
            raw=round(raw_record, 4),
            normalized=round(norm[_RECORD], 4),
            weight=params.desperate_weight_record,
            detail=(
                f"{team.wins}–{team.losses}"
                f"{f'–{team.ties}' if team.ties else ''} record, "
                f"{team.games_below_500:.0f} game(s) below .500"
            ),
        ),
        DesperateComponent(
            name=_POINTS_FOR,
            raw=round(raw_pf, 4),
            normalized=round(norm[_POINTS_FOR], 4),
            weight=params.desperate_weight_points_for,
            detail=(
                f"decay-weighted points-for in the {pct:.0f}th percentile of the league"
            ),
        ),
        DesperateComponent(
            name=_ROSTER_AGE,
            raw=round(age, 4) if age is not None else 0.0,
            normalized=round(norm[_ROSTER_AGE], 4),
            weight=params.desperate_weight_roster_age,
            detail=(
                f"roster averages {age:.1f} years"
                if age is not None
                else "no roster birthdates available"
            ),
        ),
        DesperateComponent(
            name=_BYE_CRUNCH,
            raw=round(raw_bye, 4),
            normalized=round(norm[_BYE_CRUNCH], 4),
            weight=params.desperate_weight_bye_crunch,
            detail=f"{int(raw_bye)} rostered player(s) with a bye still ahead",
        ),
    )


def desperate_team_read(
    state: TradeDeskState, params: TradeParams = DEFAULT_TRADE_PARAMS
) -> DesperateTeamRead:
    """Rank ``state.rivals`` by composite willingness to deal (methodology
    §4.9) and surface the top ``params.desperate_surface_count``."""
    rivals = state.rivals
    half_life = params.team_strength_decay_half_life_weeks

    league_pf = [
        _decay_weighted_points_for(list(t.weekly_points_for), half_life) for t in rivals
    ] + [_decay_weighted_points_for(list(state.dead_parrots_points_for), half_life)]

    raw_record = {
        t.team_id: (t.games_below_500 / t.games_played if t.games_played else 0.0)
        for t in rivals
    }
    pct_by_team = {
        t.team_id: _percentile_rank(
            _decay_weighted_points_for(list(t.weekly_points_for), half_life), league_pf
        )
        for t in rivals
    }
    raw_pf = {tid: 1.0 - pct / 100.0 for tid, pct in pct_by_team.items()}
    age_by_team = {t.team_id: _mean_roster_age(t, state) for t in rivals}
    raw_bye = {t.team_id: float(_bye_crunch_count(t, state)) for t in rivals}

    norm_record = _normalize(raw_record)
    norm_pf = _normalize(raw_pf)
    norm_age = _normalize_ages(age_by_team)
    norm_bye = _normalize(raw_bye)

    scored: list[tuple[float, str, RivalTeam, tuple[DesperateComponent, ...]]] = []
    for team in rivals:
        tid = team.team_id
        components = _components_for(
            team,
            raw_record=raw_record[tid],
            raw_pf=raw_pf[tid],
            pct=pct_by_team[tid],
            age=age_by_team[tid],
            raw_bye=raw_bye[tid],
            norm={
                _RECORD: norm_record[tid],
                _POINTS_FOR: norm_pf[tid],
                _ROSTER_AGE: norm_age[tid],
                _BYE_CRUNCH: norm_bye[tid],
            },
            params=params,
        )
        score = round(sum(c.normalized * c.weight for c in components), 6)
        scored.append((score, tid, team, components))

    scored.sort(key=lambda row: (-row[0], row[1]))
    ranked = tuple(
        DesperateTeam(
            team_id=team.team_id,
            team_name=team.team_name,
            score=score,
            rank=rank,
            components=components,
            reasons=_reasons_for(components, params),
        )
        for rank, (score, _tid, team, components) in enumerate(scored, start=1)
    )
    return DesperateTeamRead(
        ranked=ranked, surfaced=ranked[: params.desperate_surface_count]
    )
