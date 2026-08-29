from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .models import (
    FreeAgentEntry,
    FreeAgentListing,
    InjuryEntry,
    InjuryReport,
    MatchupSnapshot,
    RosterEntry,
    StandingsRow,
    StandingsSnapshot,
    TeamSide,
)
from .pages import YahooPage
from .raw import RawYahooPayload

# recorded-payload-in -> normalized-objects-out (spec issue #7, acceptance
# criterion 4). Every function here is pure: a structured payload dict in, a
# frozen domain object out, no I/O. The browser/fetch step that produces the
# payload is a separate seam and is not unit-tested.

# Tokens Yahoo renders in a numeric cell when there is no value.
_BLANK = {"", "-", "--", "---", "n/a", "na", "—"}


class YahooNormalizationError(ValueError):
    """A recorded Yahoo payload is missing structure the model depends on."""

    def __init__(self, page: YahooPage | str, message: str) -> None:
        self.page = str(page)
        super().__init__(f"{self.page}: {message}")


def _payload_dict(payload: RawYahooPayload) -> dict[str, Any]:
    try:
        data = payload.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise YahooNormalizationError(payload.page, f"payload is not valid JSON ({exc})") from exc
    if not isinstance(data, Mapping):
        raise YahooNormalizationError(payload.page, "payload is not a JSON object")
    return dict(data)


def _require(page: YahooPage, obj: Mapping[str, Any], key: str) -> Any:
    if key not in obj or obj[key] is None:
        raise YahooNormalizationError(page, f"missing required field {key!r}")
    return obj[key]


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "").replace("+", "")
    if text.lower() in _BLANK:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(page: YahooPage, value: Any, *, field: str) -> int:
    parsed = _opt_int(value)
    if parsed is None:
        raise YahooNormalizationError(page, f"{field}={value!r} is not an integer")
    return parsed


def _opt_int(value: Any) -> int | None:
    number = _opt_float(value)
    return None if number is None else int(round(number))


# --- matchup -----------------------------------------------------------------


def normalize_matchup(payload: RawYahooPayload) -> MatchupSnapshot:
    data = _payload_dict(payload)
    page = YahooPage.MATCHUP
    week = _int(page, _require(page, data, "week"), field="week")

    raw_teams = _require(page, data, "teams")
    if not isinstance(raw_teams, list) or len(raw_teams) != 2:
        raise YahooNormalizationError(page, "expected exactly two teams in the matchup")

    sides = [_team_side(page, t) for t in raw_teams]
    dead_parrots = [s for s in sides if s.is_dead_parrots]
    opponents = [s for s in sides if not s.is_dead_parrots]
    if len(dead_parrots) != 1 or len(opponents) != 1:
        raise YahooNormalizationError(
            page, "exactly one team must be flagged is_dead_parrots"
        )
    return MatchupSnapshot(week=week, dead_parrots=dead_parrots[0], opponent=opponents[0])


def _team_side(page: YahooPage, team: Any) -> TeamSide:
    if not isinstance(team, Mapping):
        raise YahooNormalizationError(page, "a team entry is not an object")
    roster = _require(page, team, "roster")
    if not isinstance(roster, list) or not roster:
        raise YahooNormalizationError(page, "a team has an empty roster")
    return TeamSide(
        team_name=str(_require(page, team, "team_name")).strip(),
        manager=_opt_str(team.get("manager")),
        is_dead_parrots=bool(team.get("is_dead_parrots", False)),
        entries=tuple(_roster_entry(page, e) for e in roster),
    )


def _roster_entry(page: YahooPage, entry: Any) -> RosterEntry:
    if not isinstance(entry, Mapping):
        raise YahooNormalizationError(page, "a roster entry is not an object")
    return RosterEntry(
        slot=str(_require(page, entry, "slot")).strip(),
        player_name=str(_require(page, entry, "name")).strip(),
        nfl_team=_opt_str(entry.get("team")),
        position=_opt_str(entry.get("position")),
        opponent=_opt_str(entry.get("opponent")),
        yahoo_projected_points=_opt_float(entry.get("projected_points")),
        injury_status=_opt_str(entry.get("injury_status")),
    )


# --- players (free agents / waiver-eligible) --------------------------------

_AVAILABILITY_ALIASES = {
    "fa": "FA",
    "free agent": "FA",
    "freeagent": "FA",
    "w": "W",
    "waiver": "W",
    "waivers": "W",
}


def normalize_players(payload: RawYahooPayload) -> FreeAgentListing:
    data = _payload_dict(payload)
    page = YahooPage.PLAYERS
    rows = _require(page, data, "players")
    if not isinstance(rows, list):
        raise YahooNormalizationError(page, "'players' is not a list")
    return FreeAgentListing(players=tuple(_free_agent(page, r) for r in rows))


def _free_agent(page: YahooPage, row: Any) -> FreeAgentEntry:
    if not isinstance(row, Mapping):
        raise YahooNormalizationError(page, "a player row is not an object")
    claim_date = _opt_str(row.get("waiver_claim_date"))
    return FreeAgentEntry(
        player_name=str(_require(page, row, "name")).strip(),
        nfl_team=_opt_str(row.get("team")),
        position=str(_require(page, row, "position")).strip(),
        availability=_availability(page, row.get("availability"), claim_date),
        waiver_claim_date=claim_date,
        percent_rostered=_opt_float(row.get("percent_rostered")),
        yahoo_projected_points=_opt_float(row.get("projected_points")),
        opponent=_opt_str(row.get("opponent")),
        injury_status=_opt_str(row.get("injury_status")),
    )


def _availability(page: YahooPage, value: Any, claim_date: str | None) -> str:
    text = _opt_str(value)
    if text is None:
        # No explicit marker: a pending claim date means it is on waivers.
        return "W" if claim_date else "FA"
    normalized = _AVAILABILITY_ALIASES.get(text.lower())
    if normalized is None:
        raise YahooNormalizationError(page, f"unknown availability {value!r}")
    return normalized


# --- injuries --------------------------------------------------------------


def normalize_injuries(payload: RawYahooPayload) -> InjuryReport:
    data = _payload_dict(payload)
    page = YahooPage.INJURIES
    rows = _require(page, data, "entries")
    if not isinstance(rows, list):
        raise YahooNormalizationError(page, "'entries' is not a list")
    return InjuryReport(entries=tuple(_injury_entry(page, r) for r in rows))


def _injury_entry(page: YahooPage, row: Any) -> InjuryEntry:
    if not isinstance(row, Mapping):
        raise YahooNormalizationError(page, "an injury row is not an object")
    return InjuryEntry(
        player_name=str(_require(page, row, "name")).strip(),
        nfl_team=_opt_str(row.get("team")),
        position=_opt_str(row.get("position")),
        status=str(_require(page, row, "status")).strip(),
        detail=_opt_str(row.get("detail")),
        updated=_opt_str(row.get("updated")),
    )


# --- standings -----------------------------------------------------------------


def normalize_standings(payload: RawYahooPayload) -> StandingsSnapshot:
    data = _payload_dict(payload)
    page = YahooPage.STANDINGS
    raw_rows = _require(page, data, "rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise YahooNormalizationError(page, "standings has no rows")

    rows = tuple(_standings_row(page, r) for r in raw_rows)
    has_priority = any(r.waiver_priority is not None for r in rows)
    return StandingsSnapshot(
        rows=rows,
        waiver_priority_source="standings" if has_priority else "manual-entry-required",
    )


def _standings_row(page: YahooPage, row: Any) -> StandingsRow:
    if not isinstance(row, Mapping):
        raise YahooNormalizationError(page, "a standings row is not an object")
    return StandingsRow(
        rank=_opt_int(row.get("rank")),
        team_name=str(_require(page, row, "team_name")).strip(),
        manager=_opt_str(row.get("manager")),
        division=_opt_str(row.get("division")),
        wins=_int(page, row.get("wins", 0), field="wins"),
        losses=_int(page, row.get("losses", 0), field="losses"),
        ties=_int(page, row.get("ties", 0), field="ties"),
        points_for=_opt_float(row.get("points_for")) or 0.0,
        points_against=_opt_float(row.get("points_against")) or 0.0,
        waiver_priority=_opt_int(row.get("waiver_priority")),
    )


NORMALIZERS: Mapping[YahooPage, Callable[[RawYahooPayload], Any]] = {
    YahooPage.MATCHUP: normalize_matchup,
    YahooPage.PLAYERS: normalize_players,
    YahooPage.INJURIES: normalize_injuries,
    YahooPage.STANDINGS: normalize_standings,
}


def normalize(payload: RawYahooPayload) -> Any:
    """Dispatch a payload to its page's normalizer."""
    try:
        normalizer = NORMALIZERS[payload.page]
    except KeyError:  # pragma: no cover - YahooPage is a closed enum
        raise YahooNormalizationError(payload.page, "no normalizer for this page") from None
    return normalizer(payload)
