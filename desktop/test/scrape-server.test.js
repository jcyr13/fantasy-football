"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { startScrapeServer } = require("../lib/scrape-server");
const { ScrapeError, YahooAuthRequiredError } = require("../lib/yahoo-extract");

const MATCHUP_URL = "https://football.fantasysports.yahoo.com/f1/735806/matchup";

// Spin up the server with an injected extract(), run `fn(baseUrl)`, tear down.
async function withServer(extract, fn) {
  const server = await startScrapeServer({ extract });
  try {
    return await fn(server.url);
  } finally {
    await server.close();
  }
}

function postScrape(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

test("startScrapeServer needs an extract function", () => {
  assert.throws(() => startScrapeServer({}), TypeError);
});

test("POST /scrape returns the extractor payload verbatim as JSON", async () => {
  const payload = { week: 3, teams: [{ team_name: "Dead Parrots" }] };
  const seen = [];
  await withServer(
    async (page, url) => {
      seen.push([page, url]);
      return payload;
    },
    async (base) => {
      const res = await postScrape(base, { page: "matchup", url: MATCHUP_URL });
      assert.equal(res.status, 200);
      assert.equal(res.headers.get("content-type"), "application/json");
      assert.deepEqual(await res.json(), payload);
      assert.deepEqual(seen, [["matchup", MATCHUP_URL]]);
    },
  );
});

test("an expired session comes back as 401 'Yahoo sign-in required'", async () => {
  await withServer(
    async () => {
      throw new YahooAuthRequiredError("standings");
    },
    async (base) => {
      const res = await postScrape(base, { page: "standings", url: "https://x/y" });
      assert.equal(res.status, 401);
      assert.equal(res.statusText, "Yahoo sign-in required");
      assert.deepEqual(await res.json(), { error: "yahoo-auth-required", page: "standings" });
    },
  );
});

test("a scrape miss is a 502 with the reason, other errors are 500", async () => {
  await withServer(
    async () => {
      throw new ScrapeError("no matching DOM tables; tables on page: 0");
    },
    async (base) => {
      const res = await postScrape(base, { page: "players", url: "https://x/y" });
      assert.equal(res.status, 502);
      // The message also rides the status line — that is all the backend's
      // urllib error keeps from a non-2xx response.
      assert.match(res.statusText, /no matching DOM tables/);
      const body = await res.json();
      assert.match(body.error, /^ScrapeError: no matching DOM tables/);
      assert.equal(body.page, "players");
    },
  );

  await withServer(
    async () => {
      throw new Error("kaboom");
    },
    async (base) => {
      const res = await postScrape(base, { page: "players", url: "https://x/y" });
      assert.equal(res.status, 500);
      assert.match((await res.json()).error, /Error: kaboom/);
    },
  );
});

test("bad route, method and body are rejected before the extractor runs", async () => {
  let called = false;
  await withServer(
    async () => {
      called = true;
      return {};
    },
    async (base) => {
      const origin = new URL(base).origin;

      assert.equal((await fetch(`${origin}/nope`, { method: "POST" })).status, 404);
      assert.equal((await fetch(base, { method: "GET" })).status, 405);

      const badJson = await postScrape(base, "{not json");
      assert.equal(badJson.status, 400);

      const badPage = await postScrape(base, { page: "roster", url: MATCHUP_URL });
      assert.equal(badPage.status, 400);

      const noUrl = await postScrape(base, { page: "matchup" });
      assert.equal(noUrl.status, 400);

      assert.equal(called, false);
    },
  );
});
