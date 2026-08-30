"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  PAGES,
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
