"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

const {
  buildBackendCommand,
  buildBackendEnv,
  waitForHealth,
  startBackend,
  stopBackend,
} = require("../lib/backend");

test("buildBackendCommand runs uvicorn on the given loopback port", () => {
  const { command, args } = buildBackendCommand({ port: 12345 });
  assert.equal(command, "uv");
  assert.deepEqual(args, [
    "run",
    "uvicorn",
    "deadparrots.app:app",
    "--host",
    "127.0.0.1",
    "--port",
    "12345",
  ]);
});

test("buildBackendCommand honours DEADPARROTS_UV_BIN and an explicit host", () => {
  const prev = process.env.DEADPARROTS_UV_BIN;
  process.env.DEADPARROTS_UV_BIN = "/opt/uv/bin/uv";
  try {
    const { command, args } = buildBackendCommand({ port: 9, host: "127.0.0.2" });
    assert.equal(command, "/opt/uv/bin/uv");
    assert.deepEqual(args.slice(-4), ["--host", "127.0.0.2", "--port", "9"]);
  } finally {
    if (prev === undefined) delete process.env.DEADPARROTS_UV_BIN;
    else process.env.DEADPARROTS_UV_BIN = prev;
  }
});

test("buildBackendCommand runs the frozen exe directly when packaged", () => {
  const prev = process.env.DEADPARROTS_UV_BIN;
  process.env.DEADPARROTS_UV_BIN = "/opt/uv/bin/uv"; // must be ignored when frozen
  try {
    const { command, args } = buildBackendCommand({
      port: 55001,
      frozenBackendExe: "C:\\Program Files\\Dead Parrots Dashboard\\resources\\backend\\deadparrots-backend.exe",
    });
    assert.equal(
      command,
      "C:\\Program Files\\Dead Parrots Dashboard\\resources\\backend\\deadparrots-backend.exe",
    );
    assert.deepEqual(args, ["--host", "127.0.0.1", "--port", "55001"]);
  } finally {
    if (prev === undefined) delete process.env.DEADPARROTS_UV_BIN;
    else process.env.DEADPARROTS_UV_BIN = prev;
  }
});

test("buildBackendEnv points the data dir at the app-data dir", () => {
  const env = buildBackendEnv({ dataDir: "/app/data" });
  assert.equal(env.DEADPARROTS_DATA_DIR, "/app/data");
  assert.equal(env.DEADPARROTS_YAHOO_EXTRACTOR_URL, undefined);
  assert.equal(env.PATH, process.env.PATH); // inherits the rest of the env
});

test("buildBackendEnv wires the Yahoo extractor endpoint when the shell has one", () => {
  const env = buildBackendEnv({
    dataDir: "/app/data",
    yahooExtractorUrl: "http://127.0.0.1:51234/scrape",
  });
  assert.equal(env.DEADPARROTS_YAHOO_EXTRACTOR_URL, "http://127.0.0.1:51234/scrape");
});

test("waitForHealth resolves once /api/health answers 200", async () => {
  let hits = 0;
  const server = http.createServer((req, res) => {
    hits += 1;
    if (req.url === "/api/health" && hits >= 2) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end('{"status":"ok"}');
    } else {
      res.writeHead(503);
      res.end();
    }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  try {
    await waitForHealth(origin, { timeoutMs: 2000, intervalMs: 20 });
    assert.ok(hits >= 2);
  } finally {
    await new Promise((r) => server.close(r));
  }
});

test("waitForHealth rejects when the backend never comes up", async () => {
  await assert.rejects(
    () => waitForHealth("http://127.0.0.1:1", { timeoutMs: 200, intervalMs: 20 }),
    /was not healthy within 200ms/,
  );
});

test("startBackend surfaces a missing launcher via onError, not a crash", async () => {
  const prev = process.env.DEADPARROTS_UV_BIN;
  process.env.DEADPARROTS_UV_BIN = "definitely-not-a-real-binary-xyz";
  try {
    const err = await new Promise((resolve) => {
      startBackend({
        backendDir: process.cwd(),
        port: 0,
        dataDir: process.cwd(),
        onError: resolve,
      });
    });
    assert.match(err.message, /was not found on PATH/);
    assert.match(err.message, /DEADPARROTS_UV_BIN/);
  } finally {
    if (prev === undefined) delete process.env.DEADPARROTS_UV_BIN;
    else process.env.DEADPARROTS_UV_BIN = prev;
  }
});

test("startBackend surfaces a missing frozen backend as a reinstall hint", async () => {
  const err = await new Promise((resolve) => {
    startBackend({
      backendDir: process.cwd(),
      port: 0,
      dataDir: process.cwd(),
      frozenBackendExe: "definitely-not-a-real-frozen-backend-xyz",
      onError: resolve,
    });
  });
  assert.match(err.message, /packaged backend/);
  assert.match(err.message, /reinstall the app/);
});

test("stopBackend is a no-op for a child that already exited", () => {
  assert.doesNotThrow(() => stopBackend(null));
  assert.doesNotThrow(() =>
    stopBackend({ pid: 999999, exitCode: 0, signalCode: null }),
  );
});
