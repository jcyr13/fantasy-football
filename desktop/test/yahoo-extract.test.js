"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { JSDOM } = require("jsdom");

const {
  PAGES,
  DEAD_PARROTS_TEAM_NAME,
  ScrapeError,
  isYahooLoginUrl,
  validateScrapePayload,
  buildExtractionScript,
} = require("../lib/yahoo-extract");

test("PAGES is exactly the four pages the backend scrapes", () => {
  assert.deepEqual([...PAGES].sort(), ["injuries", "matchup", "players", "standings"]);
});

test("isYahooLoginUrl spots the sign-in, chooser and consent gates", () => {
  for (const u of [
    "https://login.yahoo.com/?.src=fantasy&.done=https://football.fantasysports.yahoo.com/f1/735806/matchup",
    "https://guce.yahoo.com/consent?brandType=nonEu",
    "https://www.yahoo.com/account/challenge/password",
  ]) {
    assert.equal(isYahooLoginUrl(u), true, u);
  }
});

test("isYahooLoginUrl leaves the real fantasy pages alone", () => {
  for (const u of [
    "https://football.fantasysports.yahoo.com/f1/735806/matchup",
    "https://football.fantasysports.yahoo.com/f1/735806/players",
    "https://sports.yahoo.com/nfl/",
    "not a url",
    "",
    null,
  ]) {
    assert.equal(isYahooLoginUrl(u), false, String(u));
  }
});

test("validateScrapePayload passes a fixture-shaped payload for every page", () => {
  const ok = {
    matchup: {
      week: 3,
      teams: [
        { team_name: "Dead Parrots", is_dead_parrots: true, roster: [{ slot: "QB", name: "Josh Allen" }] },
        { team_name: "Norwegian Blues", is_dead_parrots: false, roster: [{ slot: "QB", name: "Jalen Hurts" }] },
      ],
    },
    players: { players: [{ name: "Jauan Jennings", position: "WR" }] },
    injuries: { entries: [{ name: "Jaylen Waddle", status: "Questionable" }] },
    standings: { rows: [{ team_name: "Norwegian Blues", wins: "3", losses: "0", ties: "0" }] },
  };
  for (const page of PAGES) {
    assert.equal(validateScrapePayload(page, ok[page]), ok[page]);
  }
});

test("validateScrapePayload rejects a scrape miss with a ScrapeError", () => {
  const bad = {
    matchup: [{}, {}], // an array, and only one team's worth
    players: {},
    injuries: { entries: "not a list" },
    standings: { rows: [] },
  };
  for (const page of PAGES) {
    assert.throws(() => validateScrapePayload(page, bad[page]), ScrapeError, page);
  }
  assert.throws(() => validateScrapePayload("matchup", null), ScrapeError);
  // An unknown page is a programmer error, not a scrape miss.
  assert.throws(() => validateScrapePayload("bogus", { week: 1 }), RangeError);
});

test("validateScrapePayload wants two fully-rostered matchup teams, exactly one flagged", () => {
  assert.throws(
    () =>
      validateScrapePayload("matchup", {
        week: 3,
        teams: [
          { team_name: "Dead Parrots", is_dead_parrots: true, roster: [{ name: "x" }] },
          { team_name: "Norwegian Blues", is_dead_parrots: false, roster: [] },
        ],
      }),
    ScrapeError,
  );
  assert.throws(
    () =>
      validateScrapePayload("matchup", {
        week: 3,
        teams: [
          { team_name: "Dead Parrots", roster: [{ name: "x" }] },
          { team_name: "Norwegian Blues", roster: [{ name: "y" }] },
        ],
      }),
    ScrapeError,
    "neither side flagged is_dead_parrots",
  );
});

test("buildExtractionScript returns an IIFE string naming the page, and rejects unknown pages", () => {
  for (const page of PAGES) {
    const src = buildExtractionScript(page);
    assert.equal(typeof src, "string");
    assert.match(src, new RegExp(`extract\\(\\s*"${page}"\\s*\\)`));
    // Parse-check the body (no execution — it references `document` / `window`)
    // so a syntax slip in the injected script can't ship silently.
    assert.doesNotThrow(() => new Function(`return ${src};`));
  }
  assert.throws(() => buildExtractionScript("teams"), RangeError);
});

// Run the injected script against saved markup in jsdom — the same string the
// Yahoo webview evaluates, so the mapper is exercised exactly as shipped.
function runScript(page, html, url = "https://football.fantasysports.yahoo.com/f1/735806") {
  const dom = new JSDOM(html, { url, runScripts: "outside-only" });
  // jsdom has no layout, so no innerText; the script only reads it as text.
  Object.defineProperty(dom.window.HTMLElement.prototype, "innerText", {
    get() {
      return this.textContent;
    },
  });
  // executeJavaScript hands back a structured clone; a JSON round trip does the
  // same here and drops jsdom's other-realm prototypes.
  return JSON.parse(JSON.stringify(dom.window.eval(buildExtractionScript(page))));
}

const fixture = (name) => fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8");

test("standings: the league-home #standingstable maps to every team's line", () => {
  const result = runScript("standings", fixture("standings-league-home.html"));
  assert.equal(result.ok, true, result.reason);
  const { rows } = validateScrapePayload("standings", result.payload);

  assert.equal(rows.length, 12);
  assert.deepEqual(rows[0], {
    rank: "2",
    team_name: "KG 55",
    manager: null,
    division: "High Tide",
    wins: 1,
    losses: 0,
    ties: 0,
    points_for: "151.22",
    points_against: "118.36",
    waiver_priority: "11",
  });
  const dp = rows.find((r) => r.team_name.includes(DEAD_PARROTS_TEAM_NAME));
  assert.equal(dp.team_name, "The Dead Parrots");
  assert.equal(dp.division, "Low Tide");
  assert.equal(dp.rank, "9");
  assert.deepEqual([dp.wins, dp.losses, dp.ties], [0, 1, 0]);
  assert.equal(dp.waiver_priority, "4");
});

test("standings: the Live Standings matchup view says it is the wrong page", () => {
  const liveStandings = `<!DOCTYPE html><html><body>
    <a href="/f1/735806/9">The Dead Parrots</a><a href="/f1/735806/4">Wild Blue</a>
    <table><thead><tr><th>Stats</th><th>Player</th><th>Proj</th><th>Fan Pts</th><th>Pos</th>
    <th>Fan Pts</th><th>Proj</th><th>Player</th><th>Stats</th></tr></thead>
    <tbody><tr><td></td><td>J. Dart</td><td>21.46</td><td>30.60</td><td>QB</td>
    <td>33.10</td><td>19.18</td><td>T. Lawrence</td><td></td></tr></tbody></table>
    </body></html>`;
  const result = runScript(
    "standings",
    liveStandings,
    "https://football.fantasysports.yahoo.com/f1/735806/standings",
  );
  assert.equal(result.ok, false);
  assert.match(result.reason, /Live Standings/);
  assert.match(result.reason, /league home/);
});
