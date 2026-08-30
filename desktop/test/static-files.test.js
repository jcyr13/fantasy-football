"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { resolveStaticFile } = require("../lib/static-files");
const { fixtureDist } = require("./helpers");

test("resolveStaticFile serves index.html for the root", () => {
  const dist = fixtureDist();
  assert.equal(resolveStaticFile(dist, "/"), path.join(dist, "index.html"));
  assert.equal(resolveStaticFile(dist, ""), path.join(dist, "index.html"));
});

test("resolveStaticFile serves a real asset by path", () => {
  const dist = fixtureDist();
  assert.equal(
    resolveStaticFile(dist, "/assets/app.js"),
    path.join(dist, "assets", "app.js"),
  );
});

test("resolveStaticFile falls back to index.html for a client-side route", () => {
  const dist = fixtureDist();
  assert.equal(resolveStaticFile(dist, "/this-week"), path.join(dist, "index.html"));
});

test("resolveStaticFile refuses path traversal", () => {
  const dist = fixtureDist();
  fs.writeFileSync(path.join(dist, "..", "outside.txt"), "secret");
  assert.equal(resolveStaticFile(dist, "/../outside.txt"), null);
  assert.equal(resolveStaticFile(dist, "/../../etc/passwd"), null);
});

test("resolveStaticFile returns null for a missing asset", () => {
  const dist = fixtureDist();
  assert.equal(resolveStaticFile(dist, "/assets/missing.js"), null);
});
