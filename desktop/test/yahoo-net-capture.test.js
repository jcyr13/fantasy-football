"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { JSDOM } = require("jsdom");

const {
  startNetCapture,
  isCandidateResponse,
  redactHeaders,
  buildBootstrapProbeScript,
} = require("../lib/yahoo-net-capture");

// Stands in for Electron's `webContents.debugger`: an EventEmitter with
// attach/detach/sendCommand. `bodies` maps a CDP requestId to what
// `Network.getResponseBody` answers (an Error rejects).
function fakeDebugger({ bodies = {}, attachError = null } = {}) {
  const dbg = new EventEmitter();
  dbg.attached = false;
  dbg.commands = [];
  dbg.isAttached = () => dbg.attached;
  dbg.attach = () => {
    if (attachError) throw attachError;
    dbg.attached = true;
  };
  dbg.detach = () => {
    dbg.attached = false;
  };
  dbg.sendCommand = async (method, params) => {
    dbg.commands.push(method);
    if (method !== "Network.getResponseBody") return {};
    const body = bodies[params.requestId];
    if (body instanceof Error) throw body;
    return body;
  };
  // What CDP emits for one request/response, in order.
  dbg.exchange = (requestId, { url, method = "GET", headers = {}, type = "XHR", status = 200, mimeType = "application/json" }) => {
    dbg.emit("message", {}, "Network.requestWillBeSent", {
      requestId,
      type,
      request: { url, method, headers },
    });
    dbg.emit("message", {}, "Network.responseReceived", {
      requestId,
      type,
      response: { url, status, mimeType },
    });
    dbg.emit("message", {}, "Network.loadingFinished", { requestId });
  };
  return dbg;
}

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "dp-net-"));
}

function readCaptures(dir, page) {
  const pageDir = path.join(dir, page);
  return fs
    .readdirSync(pageDir)
    .sort()
    .map((name) => [name, JSON.parse(fs.readFileSync(path.join(pageDir, name), "utf8"))]);
}

test("isCandidateResponse keeps JSON and XHR/fetch responses, drops page furniture", () => {
  assert.equal(isCandidateResponse({ mimeType: "application/json" }, "Script"), true);
  assert.equal(isCandidateResponse({ mimeType: "text/javascript" }, "XHR"), true);
  assert.equal(isCandidateResponse({ mimeType: "text/plain" }, "Fetch"), true);
  assert.equal(isCandidateResponse({ mimeType: "application/vnd.api+json" }, "Other"), true);
  assert.equal(isCandidateResponse({ mimeType: "image/png" }, "Image"), false);
  assert.equal(isCandidateResponse({ mimeType: "text/css" }, "Stylesheet"), false);
  assert.equal(isCandidateResponse({ mimeType: "text/html" }, "Document"), false);
  assert.equal(isCandidateResponse(undefined, "XHR"), true);
});

test("redactHeaders blanks cookie and auth values but keeps the header names", () => {
  assert.deepEqual(
    redactHeaders({ Cookie: "B=abc", authorization: "Bearer x", "X-Crumb": "c1", Accept: "*/*" }),
    { Cookie: "<redacted>", authorization: "<redacted>", "X-Crumb": "<redacted>", Accept: "*/*" },
  );
  assert.deepEqual(redactHeaders(undefined), {});
});

test("startNetCapture with no dir is a no-op that never touches the debugger", async () => {
  const dbg = fakeDebugger();
  const capture = await startNetCapture({ debugger: dbg, dir: "", page: "matchup" });
  assert.equal(dbg.attached, false);
  assert.deepEqual(await capture.stop(), { written: 0, failed: 0 });
});

test("writes each JSON response to <dir>/<page>/NNN.json with url, status and parsed body", async () => {
  const dir = tmpDir();
  const dbg = fakeDebugger({
    bodies: {
      r1: { body: '{"league":{"week":3}}', base64Encoded: false },
      r3: { body: "callback({})", base64Encoded: false },
    },
  });
  const capture = await startNetCapture({ debugger: dbg, dir, page: "matchup" });
  assert.equal(dbg.attached, true);
  assert.ok(dbg.commands.includes("Network.enable"));

  dbg.exchange("r1", {
    url: "https://football.fantasysports.yahoo.com/api/league/735806/matchup?week=3",
    headers: { Cookie: "T=secret", Accept: "application/json" },
  });
  dbg.exchange("r2", { url: "https://s.yimg.com/logo.png", type: "Image", mimeType: "image/png" });
  dbg.exchange("r3", { url: "https://example.yahoo.com/jsonp", type: "Script", mimeType: "application/json" });

  const summary = await capture.stop();
  assert.deepEqual(summary, { written: 2, failed: 0 });
  assert.equal(dbg.attached, false);

  const files = readCaptures(dir, "matchup");
  assert.deepEqual(files.map(([name]) => name), ["001.json", "002.json"]);
  const [, first] = files[0];
  assert.equal(first.url, "https://football.fantasysports.yahoo.com/api/league/735806/matchup?week=3");
  assert.equal(first.status, 200);
  assert.equal(first.method, "GET");
  assert.equal(first.resourceType, "XHR");
  assert.equal(first.mimeType, "application/json");
  assert.deepEqual(first.requestHeaders, { Cookie: "<redacted>", Accept: "application/json" });
  assert.deepEqual(first.body, { league: { week: 3 } });
  // A body that isn't JSON (JSONP, text) is kept verbatim rather than dropped.
  assert.equal(files[1][1].body, "callback({})");
  assert.equal(files[1][1].bodyIsJson, false);
});

test("decodes base64 bodies", async () => {
  const dir = tmpDir();
  const dbg = fakeDebugger({
    bodies: { r1: { body: Buffer.from('{"ok":true}').toString("base64"), base64Encoded: true } },
  });
  const capture = await startNetCapture({ debugger: dbg, dir, page: "players" });
  dbg.exchange("r1", { url: "https://x.yahoo.com/a" });
  await capture.stop();
  assert.deepEqual(readCaptures(dir, "players")[0][1].body, { ok: true });
});

test("a body CDP can't return is recorded as an error entry, not thrown", async () => {
  const dir = tmpDir();
  const dbg = fakeDebugger({ bodies: { r1: new Error("No resource with given identifier found") } });
  const capture = await startNetCapture({ debugger: dbg, dir, page: "injuries" });
  dbg.exchange("r1", { url: "https://x.yahoo.com/gone" });
  assert.deepEqual(await capture.stop(), { written: 1, failed: 1 });
  const [, entry] = readCaptures(dir, "injuries")[0];
  assert.equal(entry.url, "https://x.yahoo.com/gone");
  assert.match(entry.error, /No resource/);
  assert.equal("body" in entry, false);
});

test("a new capture of the same page clears the previous run's numbered files only", async () => {
  const dir = tmpDir();
  const pageDir = path.join(dir, "standings");
  fs.mkdirSync(pageDir, { recursive: true });
  for (const name of ["001.json", "002.json", "003.json", "notes.txt"]) {
    fs.writeFileSync(path.join(pageDir, name), "{}");
  }
  const dbg = fakeDebugger({ bodies: { r1: { body: "{}", base64Encoded: false } } });
  const capture = await startNetCapture({ debugger: dbg, dir, page: "standings" });
  dbg.exchange("r1", { url: "https://x.yahoo.com/s" });
  await capture.stop();
  assert.deepEqual(fs.readdirSync(pageDir).sort(), ["001.json", "notes.txt"]);
});

test("ignores events for requests it never saw a response for, and events after stop", async () => {
  const dir = tmpDir();
  const dbg = fakeDebugger({ bodies: { late: { body: "{}", base64Encoded: false } } });
  const capture = await startNetCapture({ debugger: dbg, dir, page: "matchup" });
  dbg.emit("message", {}, "Network.loadingFinished", { requestId: "orphan" });
  assert.deepEqual(await capture.stop(), { written: 0, failed: 0 });
  dbg.exchange("late", { url: "https://x.yahoo.com/late" });
  await new Promise((r) => setImmediate(r));
  assert.equal(fs.existsSync(path.join(dir, "matchup", "001.json")), false);
});

test("a debugger that won't attach (e.g. DevTools already open) degrades to a no-op", async () => {
  const dbg = fakeDebugger({ attachError: new Error("Another debugger is already attached") });
  const capture = await startNetCapture({ debugger: dbg, dir: tmpDir(), page: "matchup" });
  assert.deepEqual(await capture.stop(), { written: 0, failed: 0 });
});

test("a debugger it didn't attach is left attached on stop", async () => {
  const dbg = fakeDebugger();
  dbg.attached = true;
  const capture = await startNetCapture({ debugger: dbg, dir: tmpDir(), page: "matchup" });
  await capture.stop();
  assert.equal(dbg.attached, true);
});

test("buildBootstrapProbeScript reports state-like globals and inline state scripts", () => {
  const html = `<!doctype html><html><body>
    <script id="__NEXT_DATA__" type="application/json">{"props":{"week":3}}</script>
    <script>var ignored = 1;</script>
  </body></html>`;
  const dom = new JSDOM(html, { url: "https://football.fantasysports.yahoo.com/f1/735806/matchup", runScripts: "outside-only" });
  dom.window.eval(`
    window.__PRELOADED_STATE__ = { league: { id: "735806" } };
    window.YAHOO = { context: { crumb: "abc" } };
    window.somethingElse = 1;
  `);
  const probe = JSON.parse(JSON.stringify(dom.window.eval(buildBootstrapProbeScript())));
  assert.equal(probe.url, "https://football.fantasysports.yahoo.com/f1/735806/matchup");
  assert.deepEqual(probe.globals.__PRELOADED_STATE__, { league: { id: "735806" } });
  assert.deepEqual(probe.globals.YAHOO, { context: { crumb: "abc" } });
  assert.equal("somethingElse" in probe.globals, false);
  assert.equal(probe.scripts.length, 1);
  assert.equal(probe.scripts[0].id, "__NEXT_DATA__");
  assert.match(probe.scripts[0].text, /"week":3/);
});

test("buildBootstrapProbeScript survives globals that can't be serialized", () => {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only" });
  dom.window.eval(`
    const cyclic = {}; cyclic.self = cyclic;
    window.__INITIAL_STATE__ = cyclic;
  `);
  const probe = JSON.parse(JSON.stringify(dom.window.eval(buildBootstrapProbeScript())));
  assert.match(probe.globals.__INITIAL_STATE__, /^<unserializable: /);
});
