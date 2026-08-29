"""Regenerate the self-consistent fixture world for the issue #16 integration test.

Run by hand when the assembled-weekly-view pipeline intentionally changes:

    uv run python scripts/gen_weekly_fixtures.py

It writes ``tests/fixtures/weekly/`` — four nflverse payloads (player_stats,
snap_counts, rosters, schedules) and four Yahoo payloads (matchup, players,
injuries, standings) whose players resolve to one another — so
``test_weekly_integration.py`` can drive raw frames + Yahoo payloads through
``assemble_week`` → projection → simulation → every endpoint's JSON.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "weekly"

SEASON = 2026
CURRENT_WEEK = 3
COMPLETED_WEEKS = (1, 2)
NFL_TEAMS = ["BUF", "MIA", "KC", "SF", "PHI", "DAL", "CIN", "BAL"]

# id, name, nfl team, position, slot ("BN" = bench), is_dead_parrots side
# roster order matters only for readability.
DP_ROSTER = [
    ("00-1000001", "Jed Signal", "BUF", "QB", "QB"),
    ("00-1000002", "Cal Backup", "KC", "QB", "BN"),
    ("00-1000003", "Ray Carrier", "MIA", "RB", "RB"),
    ("00-1000004", "Dom Burst", "SF", "RB", "RB"),
    ("00-1000005", "Ken Spell", "PHI", "RB", "BN"),
    ("00-1000006", "Sam Deep", "KC", "WR", "WR"),
    ("00-1000007", "Vic Slant", "DAL", "WR", "WR"),
    ("00-1000008", "Ned Flat", "CIN", "WR", "W/R/T"),
    ("00-1000009", "Om Bench", "BAL", "WR", "BN"),
    ("00-1000010", "Gus Seam", "SF", "TE", "TE"),
    ("00-1000011", "Hal Block", "BUF", "TE", "BN"),
    ("00-1000012", "Poe Boot", "PHI", "K", "K"),
    ("BUF", "Bills", "BUF", "DEF", "DEF"),
    ("00-1000013", "Rex Hunt", "BAL", "LB", "D"),
]

OPP_ROSTER = [
    ("00-1000021", "Otis Arm", "KC", "QB", "QB"),
    ("00-1000022", "Bud Hold", "BUF", "QB", "BN"),
    ("00-1000023", "Alan Dash", "SF", "RB", "RB"),
    ("00-1000024", "Moe Churn", "DAL", "RB", "RB"),
    ("00-1000025", "Sy Depth", "MIA", "RB", "BN"),
    ("00-1000026", "Lee Streak", "CIN", "WR", "WR"),
    ("00-1000027", "Art Post", "BAL", "WR", "WR"),
    ("00-1000028", "Ty Wheel", "PHI", "WR", "W/R/T"),
    ("00-1000029", "Cy Pine", "BUF", "WR", "BN"),
    ("00-1000030", "Rod Hook", "KC", "TE", "TE"),
    ("00-1000031", "Van Chip", "SF", "TE", "BN"),
    ("00-1000032", "Wes Toe", "DAL", "K", "K"),
    ("SF", "49ers", "SF", "DEF", "DEF"),
    ("00-1000033", "Cliff Snap", "CIN", "S", "D"),
]

FREE_AGENTS = [
    ("00-1000041", "Free Waddle", "MIA", "WR", "FA"),
    ("00-1000042", "Wire Runner", "CIN", "RB", "W"),
    ("00-1000043", "Spare End", "BAL", "TE", "FA"),
    ("00-1000044", "Loose Kick", "KC", "K", "FA"),
    ("00-1000045", "Bench Backer", "DAL", "LB", "FA"),
    ("00-1000046", "Pocket Free", "PHI", "QB", "FA"),
    ("00-1000047", "Deep Reserve", "DAL", "WR", "W"),
    ("BAL", "Ravens", "BAL", "DEF", "FA"),
]

# team name -> (division, wins, losses, points_for, waiver_priority)
STANDINGS = [
    ("Norwegian Blues", "RIP", 3, 0, 372.4, 12),
    ("Dead Parrots", "RIP", 2, 1, 351.1, 11),
    ("Spanish Inquisition", "TIDE", 2, 1, 344.7, 10),
    ("Lumberjacks", "TIDE", 2, 1, 339.2, 9),
    ("Ministry of Walks", "RIP", 2, 1, 333.9, 8),
    ("Killer Rabbits", "TIDE", 1, 2, 328.0, 7),
    ("Spam Vikings", "RIP", 1, 2, 322.5, 6),
    ("Ex-Parrot XI", "TIDE", 1, 2, 318.1, 5),
    ("Larch Society", "RIP", 1, 2, 311.7, 4),
    ("Fjord Owners", "TIDE", 1, 2, 305.0, 3),
    ("Argument Clinic", "RIP", 0, 3, 288.3, 2),
    ("Cheese Shop", "TIDE", 0, 3, 271.9, 1),
]
OPPONENT_TEAM = "Spanish Inquisition"


def _birthdate(i: int) -> str:
    return date(1996 + (i % 6), 1 + (i % 12), 1 + (i % 27)).isoformat()


def _all_players() -> list[tuple]:
    return [*DP_ROSTER, *OPP_ROSTER, *FREE_AGENTS]


def rosters_payload() -> list[dict]:
    rows = []
    for i, (pid, name, team, pos, _slot) in enumerate(_all_players()):
        if pos == "DEF":
            continue
        rows.append(
            {
                "season": SEASON,
                "team": team,
                "position": pos,
                "full_name": name,
                "gsis_id": pid,
                "yahoo_id": f"9{i:04d}",
                "birth_date": _birthdate(i),
                "week": CURRENT_WEEK,
            }
        )
    return rows


def _game_id(week: int, away: str, home: str) -> str:
    return f"{SEASON}_{week:02d}_{away}_{home}"


def schedules_payload() -> list[dict]:
    rows = []
    for week in range(1, 15):
        teams = list(NFL_TEAMS)
        if week == 5:
            teams.remove("MIA")  # a future bye for a Dead Parrots RB
        if week == 6:
            teams.remove("SF")
        rot = teams[week % len(teams):] + teams[: week % len(teams)]
        for a, h in zip(rot[: len(rot) // 2], rot[len(rot) // 2:]):
            rows.append(
                {
                    "game_id": _game_id(week, a, h),
                    "season": SEASON,
                    "week": week,
                    "away_team": a,
                    "home_team": h,
                    "gameday": f"2026-09-{week:02d}",
                }
            )
    return rows


def _game_for(team: str, week: int, sched: list[dict]) -> str:
    for row in sched:
        if row["week"] == week and team in (row["home_team"], row["away_team"]):
            return row["game_id"]
    return ""


def _stat_line(pos: str, week: int, seed: int) -> dict:
    bump = 1.0 + 0.08 * ((seed + week) % 5 - 2)  # small deterministic week-to-week wobble
    if pos == "QB":
        return {
            "passing_yards": round(255 * bump),
            "passing_tds": 2,
            "passing_interceptions": 1,
            "rushing_yards": 14,
        }
    if pos == "RB":
        return {
            "carries": 15,
            "rushing_yards": round(72 * bump),
            "rushing_tds": 1 if week == 1 else 0,
            "targets": 4,
            "receptions": 3,
            "receiving_yards": round(21 * bump),
        }
    if pos == "WR":
        return {
            "targets": 8,
            "receptions": 5,
            "receiving_yards": round(66 * bump),
            "receiving_tds": 1 if seed % 2 == 0 else 0,
        }
    if pos == "TE":
        return {
            "targets": 5,
            "receptions": 4,
            "receiving_yards": round(41 * bump),
        }
    if pos == "K":
        return {
            "fg_made_30_39": 1,
            "fg_made_40_49": 1,
            "fg_made_50_59": 1 if week == 2 else 0,
            "pat_made": 3,
        }
    # IDP (LB/S/etc.)
    return {
        "def_tackles_solo": 5,
        "def_tackle_assists": 3,
        "def_pass_defended": 1 if week == 2 else 0,
        "def_sacks": 1.0 if seed % 3 == 0 else 0.0,
        "def_interceptions": 1 if (seed + week) % 4 == 0 else 0,
    }


def player_stats_payload(sched: list[dict]) -> list[dict]:
    rows = []
    for i, (pid, name, team, pos, _slot) in enumerate(_all_players()):
        if pos == "DEF":
            continue
        for week in COMPLETED_WEEKS:
            rows.append(
                {
                    "player_id": pid,
                    "player_name": name,
                    "player_display_name": name,
                    "position": pos,
                    "season": SEASON,
                    "week": week,
                    "season_type": "REG",
                    "game_id": _game_for(team, week, sched),
                    "team": team,
                    "opponent_team": "OPP",
                    **_stat_line(pos, week, i),
                }
            )
    return rows


def snap_counts_payload() -> list[dict]:
    rows = []
    for _pid, name, team, pos, _slot in _all_players():
        if pos not in {"RB", "WR", "TE"}:
            continue
        for week in COMPLETED_WEEKS:
            rows.append(
                {
                    "game_id": _game_id(week, team, "OPP"),
                    "season": SEASON,
                    "week": week,
                    "player": name,
                    "position": pos,
                    "team": team,
                    "opponent": "OPP",
                    "offense_snaps": 60,
                    "offense_pct": 0.82,
                }
            )
    return rows


# --- Yahoo payloads --------------------------------------------------------

_YAHOO_PROJ = {
    "QB": 21.5, "RB": 14.0, "WR": 12.5, "TE": 9.0, "K": 8.5, "DEF": 7.5,
    "LB": 10.0, "S": 9.5,
}


def _roster_entries(roster: list[tuple]) -> list[dict]:
    out = []
    for _pid, name, team, pos, slot in roster:
        status = None
        if name == "Hal Block":
            status = "Q"
        out.append(
            {
                "slot": slot,
                "name": name,
                "team": team,
                "position": pos if slot != "DEF" else "DEF",
                "opponent": "@OPP",
                "projected_points": _YAHOO_PROJ.get(pos, 8.0),
                "injury_status": status,
            }
        )
    return out


def matchup_payload() -> dict:
    return {
        "week": CURRENT_WEEK,
        "teams": [
            {
                "team_name": "Dead Parrots",
                "manager": "John",
                "is_dead_parrots": True,
                "roster": _roster_entries(DP_ROSTER),
            },
            {
                "team_name": OPPONENT_TEAM,
                "manager": "Ximenez",
                "is_dead_parrots": False,
                "roster": _roster_entries(OPP_ROSTER),
            },
        ],
    }


def players_payload() -> dict:
    rows = []
    for _pid, name, team, pos, avail in FREE_AGENTS:
        rows.append(
            {
                "name": name,
                "team": team,
                "position": "DEF" if pos == "DEF" else pos,
                "availability": avail,
                "waiver_claim_date": "Wed" if avail == "W" else None,
                "percent_rostered": "25%",
                "projected_points": _YAHOO_PROJ.get(pos, 8.0),
                "opponent": "@OPP",
                "injury_status": "Q" if name == "Free Waddle" else None,
            }
        )
    return {"players": rows}


def injuries_payload() -> dict:
    return {
        "entries": [
            {
                "name": "Hal Block",
                "team": "BUF",
                "position": "TE",
                "status": "Questionable",
                "detail": "Ankle",
                "updated": "Fri",
            },
            {
                "name": "Sy Depth",
                "team": "MIA",
                "position": "RB",
                "status": "Out",
                "detail": "Hamstring",
                "updated": "Fri",
            },
        ]
    }


def standings_payload() -> dict:
    rows = []
    for rank, (name, div, wins, losses, pf, wp) in enumerate(STANDINGS, start=1):
        rows.append(
            {
                "rank": rank,
                "team_name": name,
                "manager": name.split()[0],
                "division": div,
                "wins": wins,
                "losses": losses,
                "ties": 0,
                "points_for": pf,
                "points_against": pf - 10,
                "waiver_priority": wp,
            }
        )
    return {"rows": rows}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sched = schedules_payload()
    files = {
        "player_stats.json": player_stats_payload(sched),
        "snap_counts.json": snap_counts_payload(),
        "rosters.json": rosters_payload(),
        "schedules.json": sched,
        "matchup.json": matchup_payload(),
        "players.json": players_payload(),
        "injuries.json": injuries_payload(),
        "standings.json": standings_payload(),
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
