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

// The RIP TIDE team the owner manages. The matchup payload must flag exactly one
// side `is_dead_parrots: true` (see `normalize_matchup`); the classic Yahoo
// matchup page also renders a "My Team" marker, which the script prefers when it
// finds one. Adjust here if the team is ever renamed (CONTEXT.md "Matchup").
const DEAD_PARROTS_TEAM_NAME = "Dead Parrots";

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
      const headCells = Array.from(t.querySelectorAll("thead th, thead td"));
      const headers = headCells.map((c) => clean(c.textContent || "").toLowerCase());
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
  const colByRegex = (row, tbl, re) => {
    const i = pick(tbl, re);
    return i == null ? null : (row.cells[i] ?? null);
  };

  // "Josh Allen Buf - QB" / "Ravens Bal - DEF"  ->  { name, team, position }
  function playerCell(td) {
    if (!td) return { name: null, team: null, position: null };
    const link = td.querySelector("a");
    const name = clean(link ? link.textContent : td.textContent);
    const meta = clean((td.textContent || "").replace(name || "", ""));
    let team = null, position = null;
    const m = meta && meta.match(/([A-Za-z]{2,4})\s*[-–]\s*([A-Za-z/]+)/);
    if (m) { team = m[1]; position = m[2]; }
    const inj = td.querySelector('[class*="injury" i], [class*="status" i] abbr, abbr[title]');
    const injury_status = inj ? clean(inj.textContent) : null;
    return { name, team, position, injury_status: injury_status || null };
  }
  const firstPlayerTd = (row) =>
    Array.from(row.el.children).find((td) => td.querySelector("a")) || row.el.querySelector("td");

  // ----- players ---------------------------------------------------------
  function fromDomPlayers() {
    const t = tables().find(
      (tb) => hasHeader(tb, /player/) && hasHeader(tb, /proj|fan pts|%|owned/),
    );
    if (!t) return null;
    const players = t.rows.map((row) => {
      const p = playerCell(firstPlayerTd(row));
      const claim = colByRegex(row, t, /add|waiver|claim/);
      const waiver_claim_date = claim && !/^(add|\+|drop)$/i.test(claim) ? claim : null;
      return {
        name: p.name,
        team: p.team,
        position: p.position,
        availability: waiver_claim_date ? "W" : "FA",
        waiver_claim_date,
        percent_rostered: colByRegex(row, t, /%|owned|rostered/),
        projected_points: colByRegex(row, t, /proj/),
        opponent: colByRegex(row, t, /opp/),
        injury_status: p.injury_status,
      };
    }).filter((p) => p.name);
    return players.length ? { players } : null;
  }

  // ----- injuries ------------------------------------------------------------
  function fromDomInjuries() {
    const t = tables().find(
      (tb) => hasHeader(tb, /player/) && hasHeader(tb, /status|report|designation/),
    );
    if (!t) return null;
    const entries = t.rows.map((row) => {
      const p = playerCell(firstPlayerTd(row));
      return {
        name: p.name,
        team: p.team,
        position: p.position,
        status: colByRegex(row, t, /status|report|designation/),
        detail: colByRegex(row, t, /type|detail|injury|note/),
        updated: colByRegex(row, t, /updated|date|report date/),
      };
    }).filter((e) => e.name && e.status);
    return entries.length ? { entries } : null;
  }

  // ----- standings ---------------------------------------------------------
  function fromDomStandings() {
    const t = tables().find(
      (tb) => hasHeader(tb, /team/) && hasHeader(tb, /w-l-t|record|wins/),
    );
    if (!t) return null;
    const rows = t.rows.map((row, idx) => {
      const teamTd = firstPlayerTd(row);
      const link = teamTd && teamTd.querySelector("a");
      const team_name = clean(link ? link.textContent : (row.cells[pick(t, /team/) ?? 0]));
      const record = colByRegex(row, t, /w-l-t|record/);
      let wins = 0, losses = 0, ties = 0;
      const rm = record && record.match(/(\d+)\s*[-–]\s*(\d+)(?:\s*[-–]\s*(\d+))?/);
      if (rm) { wins = +rm[1]; losses = +rm[2]; ties = +(rm[3] || 0); }
      const rankCell = colByRegex(row, t, /rank|^#$|^pos$/);
      return {
        rank: rankCell != null ? rankCell : idx + 1,
        team_name,
        manager: clean(teamTd && teamTd.getAttribute("title")) ||
          colByRegex(row, t, /manager|owner/),
        division: colByRegex(row, t, /division|div/),
        wins, losses, ties,
        points_for: colByRegex(row, t, /^pf$|points for|pts for/),
        points_against: colByRegex(row, t, /^pa$|points against|pts against/),
        waiver_priority: colByRegex(row, t, /waiver/),
      };
    }).filter((r) => r.team_name);
    return rows.length ? { rows } : null;
  }

  // ----- matchup ---------------------------------------------------------
  function weekNumber() {
    const sel = document.querySelector('select[name="week"] option[selected], select#week option[selected]');
    if (sel) { const n = parseInt(sel.value || sel.textContent, 10); if (n) return n; }
    const m = (document.body ? document.body.innerText : "").match(/week\s+(\d{1,2})/i);
    return m ? parseInt(m[1], 10) : null;
  }
  function rosterFromTable(t) {
    return t.rows.map((row) => {
      const p = playerCell(firstPlayerTd(row));
      return {
        slot: row.cells[0],
        name: p.name,
        team: p.team,
        position: p.position,
        opponent: colByRegex(row, t, /opp/),
        projected_points: colByRegex(row, t, /proj/),
        injury_status: p.injury_status,
      };
    }).filter((e) => e.name);
  }
  function fromDomMatchup() {
    const rosterTables = tables().filter(
      (tb) => hasHeader(tb, /proj/) && tb.rows.some((r) => r.el.querySelector("a")),
    );
    if (rosterTables.length < 2) return null;
    const heads = Array.from(document.querySelectorAll(
      '.Navtarget, .matchup-team-name, [class*="team-name" i], h3, h2',
    ));
    const nameFor = (tbl) => {
      let el = tbl.el;
      for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
        const h = heads.find((x) => el.contains(x) && clean(x.textContent));
        if (h) return clean(h.textContent);
      }
      return null;
    };
    const teams = rosterTables.slice(0, 2).map((tbl) => {
      const name = nameFor(tbl);
      const block = tbl.el.closest('[class*="matchup" i], .Grid-u, section, div');
      const mine =
        (block && /my team/i.test(block.textContent || "")) ||
        (name && name.toLowerCase().includes(dp.toLowerCase()));
      return {
        team_name: name,
        manager: null,
        is_dead_parrots: !!mine,
        roster: rosterFromTable(tbl),
      };
    });
    if (teams.filter((t) => t.is_dead_parrots).length !== 1) {
      // Fall back to name match only, so exactly one side is flagged.
      teams.forEach((t) => {
        t.is_dead_parrots = !!(t.team_name && t.team_name.toLowerCase().includes(dp.toLowerCase()));
      });
    }
    const week = weekNumber();
    if (week == null || teams.some((t) => !t.roster.length)) return null;
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
    const payload = DOM[page] ? DOM[page]() : null;
    if (payload) return { ok: true, payload, via: "dom" };

    return {
      ok: false,
      via: pre ? "dom (state present, unmapped)" : "dom",
      reason:
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
