# Import pull: Yahoo pages captured outside the app

The embedded-browser assisted pull (ADR-0016) is the everyday path. When it
breaks, for example after Yahoo changes its markup and an extractor stops
matching, you can capture the same four pages another way and **import** them
(issue #55). Imported pages go through the same runner and normalizer as a live
pull:

- each page is archived to `data/yahoo/<pull_id>/<page>.json`;
- a `yahoo_pull_status` row is recorded for each page;
- the manifest records `source: "yahoo-static"`.

Nothing here uses the Yahoo Fantasy API. All data comes from your own signed-in
web session.

## Payload shapes: the fixtures are the contract

Each page is one JSON object. The authoritative examples are the recorded
fixtures the normalizer is tested against:

| Page | Fixture | Yahoo page (league 735806) |
| --- | --- | --- |
| `matchup` | [`backend/tests/fixtures/yahoo/matchup.json`](../backend/tests/fixtures/yahoo/matchup.json) | `https://football.fantasysports.yahoo.com/f1/735806/matchup` |
| `players` | [`players.json`](../backend/tests/fixtures/yahoo/players.json) | `https://football.fantasysports.yahoo.com/f1/735806/players` |
| `injuries` | [`injuries.json`](../backend/tests/fixtures/yahoo/injuries.json) | `https://football.fantasysports.yahoo.com/f1/735806/injuries` |
| `standings` | [`standings.json`](../backend/tests/fixtures/yahoo/standings.json) (or [`standings_no_waiver.json`](../backend/tests/fixtures/yahoo/standings_no_waiver.json)) | `https://football.fantasysports.yahoo.com/f1/735806?lhst=stand` (the league home's standings tab) |

If this summary and the fixtures disagree, the fixtures and
`backend/src/deadparrots/yahoo/normalize.py` are correct. Numbers can be strings
as Yahoo shows them (`"23.8"`, `"61%"`). A blank or `"-"` value is treated as
missing.

- **matchup:** `{"week": 3, "teams": [team, team]}`.
  - There must be exactly two teams, and exactly one has `"is_dead_parrots": true`.
  - A team is `{"team_name", "manager", "is_dead_parrots", "roster": [...]}`, and the roster must not be empty.
  - A roster entry needs `slot` and `name`. It may also carry `team`, `position`, `opponent`, `projected_points` and `injury_status`.
- **players:** `{"players": [...]}`.
  - Each row needs `name` and `position`.
  - `availability` is `FA` or `W` (it defaults from `waiver_claim_date`).
  - Rows may also carry `team`, `waiver_claim_date`, `percent_rostered`, `projected_points`, `opponent` and `injury_status`.
- **injuries:** `{"entries": [...]}`.
  - Each row needs `name` and `status`.
  - Rows may also carry `team`, `position`, `detail` and `updated`.
- **standings:** `{"rows": [...]}`, which must not be empty.
  - Each row needs `team_name`.
  - Rows may also carry `rank`, `manager`, `division`, `wins`, `losses`, `ties`, `points_for`, `points_against` and `waiver_priority`.
  - If no row has `waiver_priority`, the pull flags "waiver priority needs manual entry".

## Three ways to import

You can import any subset of the four pages. Only the pages you supply are
archived and normalized, and the other pages keep their latest data. A payload
the normalizer rejects is a **per-page failure** that carries the normalizer's
error. The other pages in the same import still land.

### 1. In the dashboard

Click **Import pull…** next to **Pull from Yahoo** in the data-freshness strip.
Then either:

- paste one JSON object keyed by page name, e.g.
  `{"matchup": {...}, "standings": {...}}`, or
- choose the files `matchup.json`, `players.json`, `injuries.json` and
  `standings.json` (any subset; other files are ignored). Chosen files take
  precedence over pasted text.

The result reads like an assisted pull: which pages landed, which failed and
why, and the waiver-priority reminder.

### 2. Command line

From `backend/`:

```sh
uv run python -m deadparrots.yahoo --import <dir>
```

The command reads whichever of `<dir>/{matchup,players,injuries,standings}.json`
exist.

| Exit code | Meaning |
| --- | --- |
| 0 | Every supplied page imported |
| 1 | At least one page failed (the failures are printed) |
| 2 | Nothing to import: `<dir>` is missing or has no page files |

`--week` does not combine with `--import`, because the matchup payload carries
its own week.

The CLI writes to `DEADPARROTS_DATA_DIR`, which defaults to `data`. The desktop
app keeps its data under the Electron user-data folder, which on Windows is
`%APPDATA%\Dead Parrots Dashboard\data`. To import into the installed app, set
the variable first:

```powershell
$env:DEADPARROTS_DATA_DIR = "$env:APPDATA\Dead Parrots Dashboard\data"
uv run python -m deadparrots.yahoo --import C:\path\to\yahoo-drop
```

The dashboard's **Import pull…** always writes to the running app's data, so it
needs no setup.

### 3. HTTP

`POST /api/yahoo/import` accepts a JSON object that maps one to four page names
to a payload. Each payload is either the JSON object itself or its text as a
string. The response has the same shape as `POST /api/yahoo/pull`. An empty
body, a non-object body, or an unknown page name returns `422`. The example
below targets a dev backend on its default port. The desktop app picks its own
port.

```sh
curl -X POST http://127.0.0.1:8000/api/yahoo/import \
  -H "content-type: application/json" \
  -d @payloads.json
```

## Capturing with Claude in Chrome / Cowork

Copy the prompt below into a Claude in Chrome or Cowork session, in a browser
that is **already signed in to Yahoo**. Change the folder path first if you
want the files somewhere else. Claude only reads pages, so it never needs your
password.

````text
I want you to capture four pages from my Yahoo Fantasy Football league so my
dashboard can import them. I'm already signed in to Yahoo in this browser. Only
read pages. Don't click anything that changes my team, league, or account (no
add/drop, trades, lineup changes, or claims). If a page asks me to sign in,
stop and tell me.

Save the output as four files in C:\Users\johnc\yahoo-drop\ (create the
folder, and overwrite any files already there): matchup.json, players.json,
injuries.json, standings.json. Each file is one JSON object in exactly the
shape below. Copy values as Yahoo shows them, as strings are fine, and use null
for anything blank or not shown. Don't invent data.

1. matchup.json from https://football.fantasysports.yahoo.com/f1/735806/matchup
   (my current matchup; my team is "Dead Parrots"):
   {"week": <week number>,
    "teams": [
      {"team_name": "...", "manager": "...", "is_dead_parrots": true,
       "roster": [{"slot": "QB", "name": "...", "team": "Buf", "position": "QB",
                   "opponent": "@Jax", "projected_points": "23.8",
                   "injury_status": null}, ...]},
      {"team_name": "<opponent>", "manager": "...", "is_dead_parrots": false,
       "roster": [...]}
    ]}
   Include every roster slot for both teams: starters, bench (slot "BN"), and
   IR (slot "IR"). injury_status is Yahoo's tag (e.g. "Q", "O", "IR") or null.

2. players.json from https://football.fantasysports.yahoo.com/f1/735806/players
   (the available-players list: free agents and waivers; the first page of
   results is enough):
   {"players": [{"name": "...", "team": "SF", "position": "WR",
                 "availability": "FA" or "W", "waiver_claim_date": null or "...",
                 "percent_rostered": "61%", "projected_points": "12.4",
                 "opponent": "@LAR", "injury_status": null}, ...]}

3. injuries.json from https://football.fantasysports.yahoo.com/f1/735806/injuries
   {"entries": [{"name": "...", "team": "Mia", "position": "WR",
                 "status": "Questionable", "detail": "Shoulder",
                 "updated": "Fri"}, ...]}

4. standings.json from the Standings tab of the league home page,
   https://football.fantasysports.yahoo.com/f1/735806?lhst=stand
   {"rows": [{"rank": "1", "team_name": "...", "manager": "...",
              "division": "...", "wins": "3", "losses": "0", "ties": "0",
              "points_for": "372.4", "points_against": "301.8",
              "waiver_priority": "12"}, ...]}
   Include all teams. If waiver priority isn't shown, set it to null.

When the four files are written, run this from
C:\Users\johnc\Agent Projects\fantasy-football\backend:

   $env:DEADPARROTS_DATA_DIR = "$env:APPDATA\Dead Parrots Dashboard\data"
   uv run python -m deadparrots.yahoo --import C:\Users\johnc\yahoo-drop

and show me its output. Exit code 0 means every page imported. If any page
failed, the output names the page and the problem. Fix that file to match the
shape above and run the command again. If you can't run commands, stop after
writing the files and tell me. I'll use "Import pull…" in the dashboard
instead.
````

## A failed page keeps the last good copy

A page that fails to normalize is still archived under its pull, for diagnosis.
Its manifest marks it `failed`, though, so the weekly view skips it and keeps
reading that page's last good payload. A bad import can't break **This Week**.
Fix the file and import that page again.
