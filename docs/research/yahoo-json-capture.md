# Spike: the JSON Yahoo's web app loads (issue #56)

**Status: capture flag built, findings pending a signed-in pull.**

The assisted pull reads the rendered DOM of Yahoo's React SPA (ADR-0016 §3).
Every archived failure so far has been that DOM mapping breaking. This spike
asks whether the pull could instead read the JSON that Yahoo's own web app
fetches, or the bootstrap state embedded in each page. Neither depends on CSS
or layout. ADR-0016 rejected intercepting Yahoo's XHR responses. With the
official API ruled out (`CLAUDE.md` › Constraints), that trade-off is back
open, and this doc collects the evidence.

## How to capture

The capture is off by default and never fails a pull.

1. Wait until Week 2 or later, after the Sunday games are final, so the
   matchup, projections and standings are all populated.
2. Quit the dashboard. From `desktop/`, start the shell with the flag set:

   ```powershell
   $env:DEADPARROTS_YAHOO_NET_DUMP_DIR = "$env:USERPROFILE\yahoo-net-dump"
   $env:DEADPARROTS_YAHOO_DUMP_DIR = "$env:USERPROFILE\yahoo-net-dump\html"   # optional: rendered HTML too
   npm start
   ```

3. Click **Pull from Yahoo** once. If it asks you to sign in, sign in and
   pull again. The dump for each page is overwritten on every pull.
4. Look in the dump folder:

   | Path | What it holds |
   | --- | --- |
   | `<page>/001.json`, `002.json`, … | One file per JSON-ish response the page loaded, in completion order: `url`, `status`, `method`, `resourceType`, `mimeType`, `requestHeaders` (what the page asked for), `wireHeaders` (what Chrome actually sent, which is where `Cookie` shows up), `postData` for POST/GraphQL requests, and `body` (parsed when it is JSON; `bodyIsJson` says which). An XHR/fetch that failed, or whose body Chrome couldn't return within 10 s, has `error` instead |
   | `<page>/bootstrap.dom-ready.json` | The page's state-like globals (`__PRELOADED_STATE__`, `YAHOO`, `__…__`, …) and inline JSON or state `<script>` blocks, probed as soon as the DOM exists |
   | `<page>/bootstrap.settled.json` | The same probe after the page settles. If a global is in `dom-ready` but gone here, the app deleted it on hydration: still readable, but only early |
   | `html/<page>.html` | The rendered DOM, if you set `DEADPARROTS_YAHOO_DUMP_DIR` |

   "JSON-ish" means a response with a JSON MIME type, or any XHR/fetch
   response, so JSONP and text-typed JSON aren't missed. Images, CSS, fonts and
   the HTML document are skipped.

**Don't commit the dump.** Header values that name a cookie, authorization,
crumb or token, and URL query values that name a crumb, token, auth or sig, are
replaced with `<redacted>` (in URLs it appears encoded as `%3Credacted%3E`).
Request and response bodies are written as Yahoo sent them and include your
league's data, and a crumb could still hide in a body or under an unexpected
name. Before pasting anything into this doc, trim it to the URL pattern and
field names.

Only what loads during the pull is captured. That means the page load, the
settle delay, and the extraction. Requests that fire only after scrolling,
paging or clicking a tab won't be there. Note which fields seem to need one of
those. For **players paging** in particular, the pull never clicks "next", so
check it by hand: open the players page in a normal browser, open DevTools ›
Network (filter Fetch/XHR), page forward, and note the request that fires.

**"Needs beyond cookies" is a guess until replayed.** The capture shows what
was sent, not what was required. To say a request works with cookies alone,
replay it (for example "Copy as fetch" in DevTools, with any crumb header or
query value removed) and confirm it still returns the data.

## Findings

Fill in one section per page. The target shapes are the fixtures in
`backend/tests/fixtures/yahoo/`, summarized in `docs/yahoo-import.md`.

### matchup

- **Carrying request(s):** _TBD_. Give the URL pattern, and how the league
  (735806), week and team are named in it.
- **Needs beyond cookies:** _TBD_. Note any crumb or token, and whether the
  data is only loaded after an interaction.
- **Bootstrap state:** _TBD_. Is the data in `bootstrap.dom-ready.json` or
  `bootstrap.settled.json`, or both?

| Fixture field | Present? | Where (JSON path) |
| --- | --- | --- |
| `week` | | |
| both teams: `team_name`, `manager` | | |
| which team is Dead Parrots | | |
| roster `slot` (incl. BN, IR) | | |
| `name`, `team`, `position` | | |
| `opponent` | | |
| weekly `projected_points` | | |
| `injury_status` | | |

### players

- **Carrying request(s):** _TBD_
- **Needs beyond cookies:** _TBD_
- **Paging:** _TBD_. How many rows come per request, how the next page is
  requested, and whether it's an offset or a cursor. Related: #54 (only 25
  rows).
- **Bootstrap state:** _TBD_

| Fixture field | Present? | Where (JSON path) |
| --- | --- | --- |
| `name`, `team`, `position` | | |
| `availability` (FA / W) | | |
| `waiver_claim_date` | | |
| `percent_rostered` | | |
| weekly `projected_points` | | |
| `opponent` | | |
| `injury_status` | | |

### injuries

- **Carrying request(s):** _TBD_
- **Needs beyond cookies:** _TBD_
- **Bootstrap state:** _TBD_

| Fixture field | Present? | Where (JSON path) |
| --- | --- | --- |
| `name`, `team`, `position` | | |
| `status` | | |
| `detail` | | |
| `updated` | | |

### standings

- **Carrying request(s):** _TBD_. The page is the league home
  (`/f1/735806?lhst=stand`).
- **Needs beyond cookies:** _TBD_
- **Bootstrap state:** _TBD_

| Fixture field | Present? | Where (JSON path) |
| --- | --- | --- |
| `rank`, `team_name`, `manager` | | |
| `division` | | |
| `wins`, `losses`, `ties` | | |
| `points_for`, `points_against` | | |
| **`waiver_priority`** | | |

## Recommendation

| Page | Go / no-go / partial | Source (XHR, bootstrap or DOM) | Why |
| --- | --- | --- | --- |
| matchup | _TBD_ | | |
| players | _TBD_ | | |
| injuries | _TBD_ | | |
| standings | _TBD_ | | |

A "go" on any page unblocks #57 (JSON-first mappers plus a new ADR that
supersedes ADR-0016's rejection of intercepting Yahoo's responses).

## The capture tool

- `desktop/lib/yahoo-net-capture.js` holds the capture logic, unit-tested
  against a fake debugger in `desktop/test/yahoo-net-capture.test.js`:
  - it attaches Chrome DevTools Protocol `Network` through
    `webContents.debugger`;
  - it merges `requestWillBeSent`, `requestWillBeSentExtraInfo` and
    `responseReceived`, then on `loadingFinished` fetches the body with
    `getResponseBody` (and a missing POST body with `getRequestPostData`),
    each with a 10 s timeout;
  - it records failed XHR/fetch requests from `loadingFailed`;
  - it runs the bootstrap probe and writes `bootstrap.<moment>.json`.
- `desktop/lib/yahoo-window.js` starts a capture before each page's
  `loadURL`, probes bootstrap state on `dom-ready` and again after settle, and
  stops the capture after extraction, even when the page fails.
  - If the debugger can't attach (for example because DevTools is already open
    on that window), there is no network capture, but the bootstrap probes
    still run.
  - The Electron wiring has only been exercised against the fake; the first
    real capture run is also its first live test.
