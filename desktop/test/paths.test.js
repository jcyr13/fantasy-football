"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { repoPaths, assertSpaBuilt } = require("../lib/paths");

test("repoPaths locates backend/ and frontend/dist beside desktop/", () => {
  const p = repoPaths("/repo/desktop");
  assert.equal(p.repoRoot, path.resolve("/repo"));
  assert.equal(p.backendDir, path.resolve("/repo/backend"));
  assert.equal(p.frontendDistDir, path.resolve("/repo/frontend/dist"));
});

test("the real repo layout resolves to directories that exist", () => {
  const p = repoPaths();
  assert.ok(fs.existsSync(p.backendDir), `${p.backendDir} should exist`);
});

test("assertSpaBuilt throws a build hint when index.html is missing", () => {
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "dp-nospa-"));
  assert.throws(() => assertSpaBuilt(empty), /SPA build not found/);
});

test("assertSpaBuilt passes once index.html is present", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dp-spa-"));
  fs.writeFileSync(path.join(dir, "index.html"), "<!doctype html>");
  assert.doesNotThrow(() => assertSpaBuilt(dir));
});
