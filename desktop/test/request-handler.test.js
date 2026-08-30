"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const zlib = require("node:zlib");

const { createRequestHandler } = require("../lib/request-handler");
const { fixtureDist, fakeBackend } = require("./helpers");

// A handler whose backend is never reached — for the static-file cases.
function staticHandler() {
  return createRequestHandler({
    distDir: fixtureDist(),
    backendOrigin: "http://127.0.0.1:1",
  });
}

test("serves the SPA shell for the root", async () => {
  const res = await staticHandler()(new Request("app://bundle/"));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type"), /text\/html/);
  assert.match(await res.text(), /<!doctype html>/);
});

test("serves a hashed asset with the right content type", async () => {
  const res = await staticHandler()(new Request("app://bundle/assets/app.js"));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type"), /text\/javascript/);
  assert.match(await res.text(), /export const x/);
});

test("404s an unknown asset", async () => {
  const res = await staticHandler()(new Request("app://bundle/assets/nope.js"));
  assert.equal(res.status, 404);
});

test("proxies GET /api/* to the backend, host header rewritten", async () => {
  const backend = await fakeBackend((req, res) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ path: req.url, host: req.headers.host }));
  });
  const handle = createRequestHandler({
    distDir: fixtureDist(),
    backendOrigin: backend.origin,
  });
  try {
    const res = await handle(new Request("app://bundle/api/weekly?engine=max-p-win"));
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), {
      path: "/api/weekly?engine=max-p-win",
      host: new URL(backend.origin).host, // not "bundle"
    });
  } finally {
    await backend.close();
  }
});

test("proxies a POST body through to the backend", async () => {
  const backend = await fakeBackend((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ method: req.method, echo: body }));
    });
  });
  const handle = createRequestHandler({
    distDir: fixtureDist(),
    backendOrigin: backend.origin,
  });
  try {
    const res = await handle(
      new Request("app://bundle/api/weekly/lineup-lab", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ starter_ids: ["a", "b"] }),
      }),
    );
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), {
      method: "POST",
      echo: '{"starter_ids":["a","b"]}',
    });
  } finally {
    await backend.close();
  }
});

test("returns 502 when the backend is unreachable", async () => {
  const res = await staticHandler()(new Request("app://bundle/api/health"));
  assert.equal(res.status, 502);
  assert.match(await res.text(), /backend unreachable/);
});

test("does not double-decode a gzipped backend response", async () => {
  const backend = await fakeBackend((req, res) => {
    res.writeHead(200, {
      "content-type": "application/json",
      "content-encoding": "gzip",
    });
    res.end(zlib.gzipSync(JSON.stringify({ ok: true })));
  });
  const handle = createRequestHandler({
    distDir: fixtureDist(),
    backendOrigin: backend.origin,
  });
  try {
    const res = await handle(new Request("app://bundle/api/health"));
    assert.equal(res.headers.get("content-encoding"), null);
    assert.deepEqual(await res.json(), { ok: true });
  } finally {
    await backend.close();
  }
});
