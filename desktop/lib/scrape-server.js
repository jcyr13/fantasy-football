"use strict";

const http = require("node:http");

const { PAGES, ScrapeError, YahooAuthRequiredError } = require("./yahoo-extract");

// The loopback `PageExtractor` endpoint (docs/adr/0016 §3, issue #45 — Job 2).
//
//   POST http://127.0.0.1:<port>/scrape   {"page": "matchup", "url": "https://…"}
//     200  { …the page payload in the shape `normalize` expects… }
//     401  Yahoo sign-in required          { "error": "yahoo-auth-required", "page": … }
//     502  { "error": "ScrapeError: …", "page": … }     the page gave no usable data
//     400 / 404 / 500                       malformed request / wrong route / bug
//
// The Electron main process starts this and hands the URL to the backend as
// `DEADPARROTS_YAHOO_EXTRACTOR_URL`; `build_yahoo_source(settings)` then wires
// `BrowserYahooSource(HttpPageExtractor(url))` into `app.state.yahoo_source`
// (`backend/src/deadparrots/yahoo/scrape.py`). A bare backend with the var unset
// still answers `POST /api/yahoo/pull` with 503 — untouched.
//
// `extract(page, url) -> Promise<payload>` is injected: in the app it drives the
// signed-in `persist:yahoo` webview (`./yahoo-window.js`); tests pass a fake.

const MAX_BODY_BYTES = 1 << 20; // a scrape request is a tiny JSON object

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8").trim();
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(new Error("body is not valid JSON"));
      }
    });
    req.on("error", reject);
  });
}

// An HTTP reason phrase: one line, no control chars, short enough to be sane in
// a status line.
function reasonPhrase(message) {
  return String(message || "")
    .replace(/[\r\n]+/g, " ")
    .replace(/[^\x20-\x7e]/g, "")
    .slice(0, 120)
    .trim();
}

function sendJson(res, status, obj, statusMessage) {
  const body = JSON.stringify(obj);
  res.writeHead(status, statusMessage, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function createScrapeHandler({ extract }) {
  return async function handle(req, res) {
    const pathname = new URL(req.url, "http://127.0.0.1").pathname;
    if (pathname !== "/scrape") return sendJson(res, 404, { error: "not found" });
    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "use POST" });
    }

    let body;
    try {
      body = await readJsonBody(req);
    } catch (err) {
      return sendJson(res, 400, { error: `invalid request: ${err.message}` });
    }

    const page = body && body.page;
    const url = body && body.url;
    if (!PAGES.has(page) || typeof url !== "string" || !url) {
      return sendJson(res, 400, {
        error: `expected {"page": "${[...PAGES].join(" | ")}", "url": "…"}`,
      });
    }

    try {
      const payload = await extract(page, url);
      return sendJson(res, 200, payload);
    } catch (err) {
      if (err instanceof YahooAuthRequiredError) {
        // The reason phrase rides into the backend's per-page error string
        // ("HTTPError: HTTP Error 401: Yahoo sign-in required"); Job 3 keys the
        // re-sign-in prompt off it.
        return sendJson(
          res,
          401,
          { error: "yahoo-auth-required", page },
          "Yahoo sign-in required",
        );
      }
      // `HttpPageExtractor` (backend) discards a non-2xx body, so put the useful
      // part of the message in the status line too — that is what survives into
      // the pull-status row as `str(HTTPError)`.
      const status = err instanceof ScrapeError ? 502 : 500;
      return sendJson(
        res,
        status,
        { error: `${err.name || "Error"}: ${err.message}`, page },
        reasonPhrase(err.message),
      );
    }
  };
}

// Start the endpoint on a free loopback port. Resolves to
// `{ url, port, close() }`.
function startScrapeServer({ host = "127.0.0.1", extract }) {
  if (typeof extract !== "function") {
    throw new TypeError("startScrapeServer requires an extract(page, url) function");
  }
  const server = http.createServer(createScrapeHandler({ extract }));
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, host, () => {
      const { port } = server.address();
      resolve({
        port,
        url: `http://${host}:${port}/scrape`,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}

module.exports = { startScrapeServer, createScrapeHandler };
