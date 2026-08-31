"use strict";

// The Yahoo assisted-pull extractor's *pure* half (docs/adr/0016 §3, issue #45 —
// Job 2). No Electron here: this module holds the page vocabulary, the
// signed-out detector, the payload sanity check, and the string of JavaScript
// that the main process evaluates inside the signed-in Yahoo webview.
//
// The live half — driving the embedded `persist:yahoo` window — is
// `./yahoo-window.js`. It is a browser boundary and is verified by hand against
// a real session, exactly like the backend's `BrowserYahooSource`
// (`backend/src/deadparrots/yahoo/scrape.py`).

// The four pages the assisted pull scrapes. Mirrors
// `backend/src/deadparrots/yahoo/pages.py::YahooPage`; the backend sends the
// full URL in the `/scrape` body, so this set is only used to validate the
// request and pick the right in-page mapper.
const PAGES = new Set(["matchup", "players", "injuries", "standings"]);

// John's team in the RIP TIDE League (CONTEXT.md "Dead Parrots"). The matchup
// payload must flag exactly one side `is_dead_parrots: true` (see
// `normalize_matchup`); the script matches it by name in the matchup header.
// Adjust here if the team is ever renamed.
const DEAD_PARROTS_TEAM_NAME = "Dead Parrots";

// Yahoo labels the signed-in manager's own side "My Team" in some of its
// navigation chrome. The matchup header itself uses the real team name, but a
// stray "My Team" link inside it must not be read as a team (CONTEXT.md: no
// "my team" in logic — this is the one guarded reference to Yahoo's own label).
const YAHOO_SELF_LABEL = "My Team";

class ScrapeError extends Error {
  constructor(message) {
    super(message);
    this.name = "ScrapeError";
  }
}

// A signed-out / expired Yahoo session. The `/scrape` server turns this into a
// `401 Yahoo sign-in required` response; the backend records that as a per-page
// failure whose error text carries the phrase, and Job 3 (#46) reads it to
// prompt a re-sign-in. Never a silent success.
class YahooAuthRequiredError extends Error {
  constructor(page) {
    super(`Yahoo sign-in required to scrape "${page}"`);
    this.name = "YahooAuthRequiredError";
    this.page = page;
  }
}

// Hosts Yahoo bounces an unauthenticated request through: the login form, the
// account chooser, and the GDPR consent gate ("guce"). Shared with the injected
// script (`SCRIPT_BODY` below, via `JSON.stringify`) so the two can't drift.
const YAHOO_LOGIN_HOSTS = ["login.yahoo.com", "consent.yahoo.com"];
const YAHOO_LOGIN_HOST_PREFIXES = ["guce."];

// If the webview lands on one of those hosts (or a Yahoo `/account/...`
// challenge path) instead of the fantasy page, the session is gone.
function isYahooLoginUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== "string") return false;
  let u;
  try {
    u = new URL(rawUrl);
  } catch {
    return false;
  }
  const host = u.hostname.toLowerCase();
  if (YAHOO_LOGIN_HOSTS.includes(host)) return true;
  if (YAHOO_LOGIN_HOST_PREFIXES.some((prefix) => host.startsWith(prefix))) return true;
  if (
    (host.endsWith(".yahoo.com") || host === "yahoo.com") &&
    /^\/account\/(?:challenge|logins?|module)/.test(u.pathname)
  ) {
    return true;
  }
  return false;
}

// The top-level key(s) each page's normalizer dereferences first
// (`backend/src/deadparrots/yahoo/normalize.py`). A payload that does not even
// have these is a scrape miss — a wrong page, an empty SPA shell, a consent
// wall — not something to hand the backend as a confusing "missing required
// field" further down.
const REQUIRED_KEY = {
  matchup: (p) =>
    p.week != null &&
    Array.isArray(p.teams) &&
    p.teams.length === 2 &&
    p.teams.every((t) => t && Array.isArray(t.roster) && t.roster.length > 0) &&
    // `normalize_matchup` rejects anything but exactly one flagged side.
    p.teams.filter((t) => t.is_dead_parrots).length === 1,
  players: (p) => Array.isArray(p.players),
  injuries: (p) => Array.isArray(p.entries),
  standings: (p) => Array.isArray(p.rows) && p.rows.length > 0,
};

function validateScrapePayload(page, payload) {
  if (!PAGES.has(page)) throw new RangeError(`unknown Yahoo page "${page}"`);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ScrapeError(`${page}: extractor returned ${payload === null ? "null" : typeof payload}, expected an object`);
  }
  if (!REQUIRED_KEY[page](payload)) {
    throw new ScrapeError(
      `${page}: payload is missing the structure the normalizer needs ` +
        `(got keys: ${Object.keys(payload).join(", ") || "none"}) — the page may not have finished loading, or the session may be signed out`,
    );
  }
  return payload;
}

// --- the injected extraction script ----------------------------------------
//
// Evaluated by `webContents.executeJavaScript` in the Yahoo page's own world.
// It returns a JSON-serializable object:
//
//   { ok: true, payload: {...}, via: "state" | "dom" }   success
//   { ok: false, reason, via }                            page loaded, no data
//   { authRequired: true }                                a login / consent gate
//
// The `payload` shape per page is the contract recorded in
// `backend/tests/fixtures/yahoo/*.json` — keep the two in step.
//
// PRIMARY path is the rendered DOM: `football.fantasysports.yahoo.com/f1/<id>/<page>`
// still serves the "classic" fantasy UI with real HTML tables. `__PRELOADED_STATE__`
// is checked first and used when present and mappable, per docs/adr/0016 §3.
//
// NOTE (#45): the DOM selectors below are header-text driven rather than tied to
// Yahoo's hashed class names, but they are a first cut. The first live pull is
// the place to confirm each page against the real markup and tighten the
// mappers; `reason` / `via` in the return value are built to make that fast.

const SCRIPT_BODY = String.raw`
  const clean = (s) => (s == null ? null : String(s).replace(/\s+/g, " ").trim() || null);
  const dp = ${JSON.stringify(DEAD_PARROTS_TEAM_NAME)};
  const SELF_LABEL = ${JSON.stringify(YAHOO_SELF_LABEL)}.toLowerCase();
  const LOGIN_HOSTS = ${JSON.stringify(YAHOO_LOGIN_HOSTS)};
  const LOGIN_HOST_PREFIXES = ${JSON.stringify(YAHOO_LOGIN_HOST_PREFIXES)};

  function looksLikeLogin() {
    const h = location.hostname.toLowerCase();
    if (LOGIN_HOSTS.includes(h) || LOGIN_HOST_PREFIXES.some((p) => h.startsWith(p))) return true;
    return /sign in to yahoo|log in to your account/i.test(document.body ? document.body.innerText.slice(0, 4000) : "");
  }

  function preloadedState() {
    for (const g of ["__PRELOADED_STATE__", "__INITIAL_STATE__", "__NUXT__"]) {
      try {
        const v = window[g];
        if (v && typeof v === "object") return { name: g, state: v };
      } catch (e) { /* cross-origin frame guard */ }
    }
    return null;
  }

  // Read every data table on the page into { headers:[lowercased], rows:[{by, cells, text}] }.
  function tables() {
    return Array.from(document.querySelectorAll("table")).map((t) => {
      // Yahoo's stat tables stack two <thead> rows: group labels ("Passing")
      // over the real column headers ("Yds", "TD"), the first row full of
      // colspans. Only the LAST thead row lines up one-to-one with the body
      // <td>s, so index-based column lookup has to read from that row alone.
      const headRows = Array.from(t.querySelectorAll("thead tr"));
      const headCells = headRows.length
        ? Array.from(headRows[headRows.length - 1].querySelectorAll("th, td"))
        : [];
      // clean() returns null for an empty cell (Yahoo's icon-only / checkbox
      // header columns), so coalesce before lowercasing — a bare .toLowerCase()
      // here threw and aborted the whole extraction ("via exception").
      const headers = headCells.map((c) => (clean(c.textContent) || "").toLowerCase());
      const bodyRows = Array.from(t.querySelectorAll("tbody tr")).filter(
        (tr) => tr.querySelector("td"),
      );
      const rows = bodyRows.map((tr) => {
        const tds = Array.from(tr.children);
        const cells = tds.map((td) => clean(td.textContent || ""));
        const by = {};
        headers.forEach((h, i) => { if (h) by[h] = cells[i] ?? null; });
        return { by, cells, el: tr, text: clean(tr.textContent || "") };
      });
      return { el: t, headers, rows };
    });
  }

  const hasHeader = (tbl, re) => tbl.headers.some((h) => h && re.test(h));
  const pick = (tbl, re) => {
    const i = tbl.headers.findIndex((h) => h && re.test(h));
    return i < 0 ? null : i;
  };
  // One row cell by column index, tolerant of the "not found" sentinels both
  // pick() (null) and Array#indexOf (-1) return.
  const cellAt = (row, i) => (i == null || i < 0 ? null : (row.cells[i] ?? null));
  const colByRegex = (row, tbl, re) => cellAt(row, pick(tbl, re));

  // A Yahoo player cell — the same DOM shape on the matchup, players and
  // injuries pages: a .ysf-player-name block holding the name link, an optional
  // injury badge (.ysf-player-status, its title attr = the long form), a
  // "Team - POS" span, and a .ysf-game-status line ("Sun 1:00 pm @ Det").
  //   -> { name, team, position, injury_code, injury_label, opponent }
  function playerCell(td) {
    const empty = {
      name: null, team: null, position: null,
      injury_code: null, injury_label: null, opponent: null,
    };
    if (!td) return empty;
    const nameEl =
      td.querySelector("a.name") ||
      td.querySelector(".ysf-player-name a[href]") ||
      td.querySelector("a[data-ys-playerid]");
    const name = clean(
      nameEl ? nameEl.textContent || nameEl.getAttribute("title") : td.textContent,
    );
    if (!name) return empty;

    let team = null, position = null;
    // "Team - POS" always renders spaced ("NO - WR", "KC - RB"). The injury
    // badge inside .ysf-player-status can hold a dashed code ("IR-R", "PUP-P")
    // that a spaceless pattern would grab first, so skip that subtree and
    // require the spaces.
    const tp = Array.from(td.querySelectorAll("span"))
      .filter((s) => !(s.closest && s.closest(".ysf-player-status")))
      .map((s) => clean(s.textContent))
      .find((x) => x && /^[A-Za-z.]{2,4}\s+[-–]\s+[A-Za-z/]{1,6}$/.test(x));
    if (tp) {
      const m = tp.match(/^([A-Za-z.]{2,4})\s+[-–]\s+([A-Za-z/]{1,6})$/);
      team = m[1];
      position = m[2];
    }

    const badge = td.querySelector(".ysf-player-status [title], .ysf-player-status abbr, .ysf-player-status span");
    const injury_code = badge ? clean(badge.textContent) : null;
    const injury_label = badge
      ? clean((badge.getAttribute && badge.getAttribute("title")) || "") || injury_code
      : null;

    let opponent = null;
    const gs = td.querySelector(".ysf-game-status");
    const gm = gs && (gs.textContent || "").match(/(@|vs)\s*([A-Za-z]{2,4})\b/i);
    if (gm) opponent = (/^@/.test(gm[1]) ? "@" : "vs ") + gm[2];

    return { name, team, position, injury_code, injury_label, opponent };
  }
  // On the players and injuries pages the player-name cell carries a bare
  // "player" class token ("Alt Ta-start player"). The matchup page has no such
  // token — its player cells are found by header-index instead (fromDomMatchup).
  const playerTd = (row) => row.el.querySelector("td.player");

  // ----- players ---------------------------------------------------------
  function fromDomPlayers() {
    // The free-agent table has a td.player name column and an "Add player"
    // link in every row; the page's other <table>s are stat-abbreviation keys.
    const t = tables().find(
      (tbl) => tbl.el.querySelector("td.player") && tbl.el.querySelector('a[href*="addplayer?"]'),
    );
    if (!t) return null;

    // "% Ros" is the roster share; "% Ros (diamond)" — Yahoo's premium column —
    // sits right next to it, so match the plain header only.
    const rosIdx = pick(t, /^%\s*ros$/);
    // The Pre-Season / Actual stat view carries only a season-total "Fan Pts",
    // no per-week projection. Leave projected_points null rather than pass a
    // season total into a per-week field (docs/adr/0016 §3 — deferred tuning).
    const projIdx = pick(t, /\bproj/);

    const players = t.rows
      .map((row) => {
        const pcTd = playerTd(row);
        const p = playerCell(pcTd);
        // The cell right after the name is "Roster Status": "FA", "W", or a
        // pending waiver-claim date ("Wed").
        const rs = clean(
          pcTd && pcTd.nextElementSibling ? pcTd.nextElementSibling.textContent : "",
        );
        let availability = null;
        let waiver_claim_date = null;
        if (!rs || /^FA\b/i.test(rs)) availability = "FA";
        else if (/^W\b/i.test(rs) || /waiver/i.test(rs)) availability = "W";
        else waiver_claim_date = rs; // a date -> normalize infers "W"
        return {
          name: p.name,
          team: p.team,
          position: p.position,
          availability,
          waiver_claim_date,
          percent_rostered: cellAt(row, rosIdx),
          projected_points: cellAt(row, projIdx),
          opponent: p.opponent,
          injury_status: p.injury_code,
        };
      })
      .filter((p) => p.name && p.position); // normalize requires both
    return players.length ? { players } : null;
  }

  // ----- injuries ------------------------------------------------------------
  function fromDomInjuries() {
    const t = tables().find(
      (tbl) => tbl.el.querySelector("td.player") && hasHeader(tbl, /injury|designation|status/),
    );
    if (!t) return null;
    const detailIdx = pick(t, /injury type|type|detail/);
    const updatedIdx = pick(t, /updated|report date|as of/);
    const entries = t.rows
      .map((row) => {
        const p = playerCell(playerTd(row));
        return {
          name: p.name,
          team: p.team,
          position: p.position,
          // The status pill's long form: "Questionable", "Suspended", "Out"...
          // The modern injuries page has no separate status column — the pill is
          // the only source (verified against a signed-in dump, docs/adr/0016).
          status: p.injury_label || p.injury_code,
          detail: cellAt(row, detailIdx),
          updated: cellAt(row, updatedIdx),
        };
      })
      .filter((e) => e.name && e.status);
    return entries.length ? { entries } : null;
  }

  // ----- standings ---------------------------------------------------------
  function fromDomStandings() {
    // The real standings grid: a "Team" column beside a W-L-T / record / PCT one.
    const t = tables().find(
      (tbl) => hasHeader(tbl, /team/) && hasHeader(tbl, /w-l-t|record|wins|pct/),
    );
    if (t) {
      const teamI = pick(t, /team/) ?? 0;
      const rows = t.rows
        .map((row, idx) => {
          const teamTd = row.el.children[teamI];
          const link = teamTd && teamTd.querySelector("a");
          const team_name = clean(link ? link.textContent : row.cells[teamI]);
          const record = colByRegex(row, t, /w-l-t|record/);
          let wins = 0, losses = 0, ties = 0;
          const rm = record && record.match(/(\d+)\s*[-–]\s*(\d+)(?:\s*[-–]\s*(\d+))?/);
          if (rm) { wins = +rm[1]; losses = +rm[2]; ties = +(rm[3] || 0); }
          const rankCell = colByRegex(row, t, /rank|^#$|^pos$/);
          return {
            rank: rankCell != null ? rankCell : idx + 1,
            team_name,
            manager:
              // "owner" here is a Yahoo standings-header token, not the repo's
              // vocabulary (CONTEXT.md: the person is a "Manager").
              clean(teamTd && teamTd.getAttribute("title")) ||
              colByRegex(row, t, /manager|owner/),
            division: colByRegex(row, t, /division|div/),
            wins, losses, ties,
            points_for: colByRegex(row, t, /^pf$|points for|pts for/),
            points_against: colByRegex(row, t, /^pa$|points against|pts against/),
            waiver_priority: colByRegex(row, t, /waiver/),
          };
        })
        .filter((r) => r.team_name);
      return rows.length ? { rows } : null;
    }

    // Preseason: /f1/<id>/standings still renders the matchup grid (S / BN
    // player stat tables) — no standings until week 1 games are final. Say so
    // honestly rather than fabricate zero-filled rows.
    const teamIds = new Set(
      Array.from(document.querySelectorAll('a[href*="/f1/"]'))
        .map((a) => (a.getAttribute("href") || "").match(/\/f1\/\d+\/(\d+)(?:$|[/?#])/))
        .filter(Boolean)
        .map((m) => m[1]),
    );
    if (teamIds.size >= 2) {
      return {
        __reason:
          "the Live Standings page is still the preseason matchup grid (" +
          teamIds.size +
          " team links, no W-L-T table) — re-pull once week 1 games are final",
      };
    }
    return null;
  }

  // ----- matchup ---------------------------------------------------------
  function weekNumber() {
    const nav = document.querySelector("#matchup_selectlist_nav");
    let m = nav && (nav.getAttribute("title") || "").match(/week\s+(\d{1,2})/i);
    if (m) return parseInt(m[1], 10);
    const opt = document.querySelector(
      'select[name="week"] option[selected], select#week option[selected]',
    );
    if (opt) {
      m =
        (opt.value || "").match(/(?:week=)?(\d{1,2})/) ||
        (opt.textContent || "").match(/week\s+(\d{1,2})/i);
      if (m) return parseInt(m[1], 10);
    }
    const flt = document.querySelector(".flyout-title, .flyout_trigger");
    m = flt && (flt.textContent || "").match(/week\s+(\d{1,2})/i);
    if (m) return parseInt(m[1], 10);
    m = (document.body ? document.body.innerText : "").match(/week\s+(\d{1,2})/i);
    return m ? parseInt(m[1], 10) : null;
  }

  // The two named teams from #matchup-header, in DOM order (on your own matchup
  // view Yahoo renders your team first / left, the opponent second / right —
  // the same order as the stat tables' left and right player columns).
  function matchupHeads() {
    const header = document.querySelector("#matchup-header");
    if (!header) return [];
    const out = [];
    const seen = new Set();
    for (const a of Array.from(header.querySelectorAll('a[href*="/f1/"]'))) {
      const href = a.getAttribute("href") || "";
      if (!/\/f1\/\d+\/\d+(?:$|[/?#])/.test(href)) continue;
      const team_name = clean(a.textContent);
      if (!team_name || team_name.toLowerCase() === SELF_LABEL) continue;
      const key = team_name.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      let manager = null;
      let scope = a.parentElement;
      for (let i = 0; i < 4 && scope && !manager; i++, scope = scope.parentElement) {
        const u = scope.querySelector(".user-id");
        if (u) manager = clean(u.textContent);
      }
      out.push({ team_name, manager });
    }
    return out;
  }

  function fromDomMatchup() {
    // statTable1 (starters) + statTable2 (bench/IR): both carry the Datatable
    // class and .ysf-player-name cells. Every row mirrors BOTH rosters:
    //   [_, playerL, projL, fanPtsL, pos, pos, pos, fanPtsR, projR, playerR, _]
    const rosterTables = tables().filter(
      (tbl) => /datatable/i.test(tbl.el.className) && tbl.el.querySelector(".ysf-player-name"),
    );
    if (!rosterTables.length) return null;

    const heads = matchupHeads();
    if (heads.length !== 2) {
      return {
        __reason:
          "the matchup header did not resolve to two teams (read as " +
          JSON.stringify(heads.map((h) => h.team_name)) + ")",
      };
    }
    const dpIdx = heads.findIndex((h) => h.team_name.toLowerCase().includes(dp.toLowerCase()));
    if (dpIdx < 0) {
      return {
        __reason:
          'neither matchup side is "' + dp + '" (header read as ' +
          JSON.stringify(heads.map((h) => h.team_name)) + ")",
      };
    }

    const rosters = [[], []];
    for (const tbl of rosterTables) {
      const pL = tbl.headers.indexOf("player");
      const pR = tbl.headers.lastIndexOf("player");
      if (pL < 0 || pR <= pL) continue;
      const jL = tbl.headers.indexOf("proj");
      const jR = tbl.headers.lastIndexOf("proj");
      const midI = Math.floor((pL + pR) / 2);
      // Every row mirrors both matchup sides: the left team reads from the first
      // "player"/"proj" header pair, the right team from the last.
      const sides = [
        { playerCol: pL, projCol: jL, roster: rosters[0] },
        { playerCol: pR, projCol: jR, roster: rosters[1] },
      ];
      for (const row of tbl.rows) {
        const tds = Array.from(row.el.children);
        const slotEl = row.el.querySelector(".pos-label[data-pos]");
        const slot =
          (slotEl && clean(slotEl.getAttribute("data-pos"))) ||
          (tds[midI] && clean(tds[midI].textContent)) ||
          null;
        for (const side of sides) {
          const p = playerCell(tds[side.playerCol]);
          if (!p.name) continue;
          side.roster.push({
            slot: slot || p.position || "?",
            name: p.name,
            team: p.team,
            position: p.position,
            opponent: p.opponent,
            projected_points: cellAt(row, side.projCol),
            injury_status: p.injury_code,
          });
        }
      }
    }

    const week = weekNumber();
    if (week == null) {
      return {
        __reason:
          "found both matchup rosters but no week number (checked #matchup_selectlist_nav, " +
          "the week <select>, and the page text)",
      };
    }
    const teams = heads.map((h, i) => ({
      team_name: h.team_name,
      manager: h.manager,
      is_dead_parrots: i === dpIdx,
      roster: rosters[i],
    }));
    if (teams.some((t) => !t.roster.length)) {
      return {
        __reason:
          "a matchup side parsed to zero players (roster sizes " +
          JSON.stringify(teams.map((t) => t.roster.length)) + ")",
      };
    }
    return { week, teams };
  }

  const DOM = {
    matchup: fromDomMatchup,
    players: fromDomPlayers,
    injuries: fromDomInjuries,
    standings: fromDomStandings,
  };

  function extract(page) {
    if (looksLikeLogin()) return { authRequired: true };

    const pre = preloadedState();
    // __PRELOADED_STATE__ is captured for diagnostics and future mapping; the
    // classic-UI DOM is the shape the fixtures were built from, so it wins when
    // it produces a payload. (#45: add a state->payload mapper here once the
    // real bootstrap shape is known.)
    const out = DOM[page] ? DOM[page]() : null;
    if (out && !out.__reason) return { ok: true, payload: out, via: "dom" };

    return {
      ok: false,
      via: pre ? "dom (state present, unmapped)" : "dom",
      reason:
        (out && out.__reason ? out.__reason + "; " : "") +
        (pre ? "found " + pre.name + " but no DOM tables matched; " : "no matching DOM tables; ") +
        "tables on page: " + document.querySelectorAll("table").length,
    };
  }
`;

function buildExtractionScript(page) {
  if (!PAGES.has(page)) {
    throw new RangeError(`unknown Yahoo page ${JSON.stringify(page)}`);
  }
  return `(() => {
    ${SCRIPT_BODY}
    try {
      return extract(${JSON.stringify(page)});
    } catch (e) {
      return { ok: false, via: "exception", reason: String((e && e.message) || e) };
    }
  })()`;
}

module.exports = {
  PAGES,
  DEAD_PARROTS_TEAM_NAME,
  ScrapeError,
  YahooAuthRequiredError,
  isYahooLoginUrl,
  validateScrapePayload,
  buildExtractionScript,
};
