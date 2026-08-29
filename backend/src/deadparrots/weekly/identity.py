from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

# Player identity resolution between a Yahoo scrape (display names) and nflverse
# (``player_id`` / ``gsis_id`` plus ``player_name`` spellings like ``"J.Allen"``).
# There is no shared key, so this is a best-effort normalized-name match against
# the ``rosters`` frame — see ADR-0013 §2. A Yahoo player that does not resolve
# is never dropped: the caller keeps a synthetic id and falls back to the Yahoo
# projection for the mean.

__all__ = [
    "ResolvedPlayer",
    "PlayerResolver",
    "normalize_name",
    "synthetic_id",
]

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Yahoo renders a team defense as the nickname ("Cardinals"); map the ones the
# RIP TIDE league can roster to the nflverse team abbreviation.
_DEF_NICKNAMES: Mapping[str, str] = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "raiders": "LV", "chargers": "LAC", "rams": "LAR", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF",
    "niners": "SF", "seahawks": "SEA", "buccaneers": "TB", "titans": "TEN",
    "commanders": "WAS",
}

# Yahoo abbreviations that differ from nflverse's.
_TEAM_ALIASES: Mapping[str, str] = {
    "JAC": "JAX", "WSH": "WAS", "LAR": "LAR", "LA": "LAR", "OAK": "LV",
    "SD": "LAC", "STL": "LAR", "GNB": "GB", "KAN": "KC", "NWE": "NE",
    "NOR": "NO", "SFO": "SF", "TAM": "TB",
}


def normalize_name(name: str) -> str:
    """Casefold, drop accents and punctuation, strip a generational suffix, and
    collapse whitespace — the key both sides of the match are indexed on."""
    folded = unicodedata.normalize("NFKD", name or "")
    folded = folded.encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^a-zA-Z0-9\s]", " ", folded).casefold()
    parts = [p for p in folded.split() if p]
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def normalize_team(team: str | None) -> str | None:
    """Upper-case a team abbreviation and map Yahoo spellings onto nflverse's."""
    if not team:
        return None
    key = team.strip().upper()
    return _TEAM_ALIASES.get(key, key)


def _initial_last(name: str) -> str:
    """``"Josh Allen"`` → ``"j allen"`` — the nflverse ``player_name`` short
    form. Returns ``""`` when the name has fewer than two tokens."""
    parts = normalize_name(name).split()
    if len(parts) < 2:
        return ""
    return f"{parts[0][0]} {parts[-1]}"


def synthetic_id(name: str) -> str:
    """A stable id for a Yahoo player that did not resolve to nflverse."""
    slug = re.sub(r"\s+", "-", normalize_name(name)) or "unknown"
    return f"yahoo:{slug}"


@dataclass(frozen=True)
class ResolvedPlayer:
    """One nflverse identity a Yahoo name matched to."""

    player_id: str
    full_name: str
    nfl_team: str | None
    position: str | None
    birth_date: date | None
    resolved: bool = True


def _parse_birth_date(value: object) -> date | None:
    if value in (None, "", "NA"):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class PlayerResolver:
    """Name → nflverse ``player_id`` lookup built from the ``rosters`` frame.

    Rows are plain mappings (the data provider converts the parquet frame to
    dicts) with at least ``full_name``, ``team``, ``position`` and — when
    present — ``gsis_id`` / ``player_id``, ``yahoo_id`` and ``birth_date``.
    Indexed both on ``(normalized full name, team)`` and, more loosely, on the
    normalized ``"F.Last"`` form and the bare full name.
    """

    def __init__(self, roster_rows: Iterable[Mapping[str, object]]) -> None:
        self._by_name_team: dict[tuple[str, str], ResolvedPlayer] = {}
        self._by_name: dict[str, ResolvedPlayer] = {}
        self._by_initial_team: dict[tuple[str, str], ResolvedPlayer] = {}
        self._by_yahoo_id: dict[str, ResolvedPlayer] = {}
        self._ambiguous_names: set[str] = set()

        for row in roster_rows:
            name = str(row.get("full_name") or row.get("player_name") or "").strip()
            if not name:
                continue
            pid = str(
                row.get("gsis_id") or row.get("player_id") or row.get("smart_id") or ""
            ).strip()
            if not pid:
                continue
            team = normalize_team(
                str(row.get("team") or row.get("recent_team") or "") or None
            )
            resolved = ResolvedPlayer(
                player_id=pid,
                full_name=name,
                nfl_team=team,
                position=(str(row.get("position") or "") or None),
                birth_date=_parse_birth_date(row.get("birth_date")),
            )
            norm = normalize_name(name)
            if norm in self._by_name and self._by_name[norm].player_id != pid:
                self._ambiguous_names.add(norm)
            self._by_name.setdefault(norm, resolved)
            if team:
                self._by_name_team[(norm, team)] = resolved
                init = _initial_last(name)
                if init:
                    self._by_initial_team[(init, team)] = resolved
            yid = str(row.get("yahoo_id") or "").strip()
            if yid and yid != "None":
                self._by_yahoo_id[yid] = resolved

    def resolve(
        self,
        name: str,
        *,
        team: str | None = None,
        position: str | None = None,
        yahoo_id: str | None = None,
    ) -> ResolvedPlayer | None:
        """The nflverse identity for a Yahoo player, or ``None`` if no confident
        match exists."""
        if yahoo_id and yahoo_id in self._by_yahoo_id:
            return self._by_yahoo_id[yahoo_id]

        role = (position or "").strip().upper()
        if role in {"DEF", "DST", "D/ST"}:
            abbr = _DEF_NICKNAMES.get(normalize_name(name)) or normalize_team(team)
            if abbr:
                return ResolvedPlayer(
                    player_id=abbr,
                    full_name=name,
                    nfl_team=abbr,
                    position="DEF",
                    birth_date=None,
                )
            return None

        norm = normalize_name(name)
        nteam = normalize_team(team)
        if nteam and (norm, nteam) in self._by_name_team:
            return self._by_name_team[(norm, nteam)]
        init = _initial_last(name)
        if nteam and init and (init, nteam) in self._by_initial_team:
            return self._by_initial_team[(init, nteam)]
        if norm in self._by_name and norm not in self._ambiguous_names:
            return self._by_name[norm]
        return None

    def resolve_or_synthetic(
        self,
        name: str,
        *,
        team: str | None = None,
        position: str | None = None,
        yahoo_id: str | None = None,
    ) -> ResolvedPlayer:
        """Always returns an identity: a real one, or a synthetic
        ``resolved=False`` placeholder keyed off the Yahoo name."""
        hit = self.resolve(name, team=team, position=position, yahoo_id=yahoo_id)
        if hit is not None:
            return hit
        return ResolvedPlayer(
            player_id=synthetic_id(name),
            full_name=name,
            nfl_team=normalize_team(team),
            position=(position or None),
            birth_date=None,
            resolved=False,
        )
