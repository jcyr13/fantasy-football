"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  repoPaths,
  appPaths,
  assertSpaBuilt,
  assertBackendBuilt,
  BACKEND_EXE_NAME,
} = require("../lib/paths");

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

test("appPaths in dev mode is the repo layout, with no frozen backend", () => {
  const p = appPaths({ isPackaged: false, desktopDir: "/repo/desktop" });
  assert.equal(p.backendDir, path.resolve("/repo/backend"));
  assert.equal(p.frontendDistDir, path.resolve("/repo/frontend/dist"));
  assert.equal(p.frozenBackendExe, null);
});

test("appPaths in packaged mode points at resources/ and the frozen exe", () => {
  const res = path.join("/opt", "app", "resources");
  const p = appPaths({ isPackaged: true, resourcesPath: res });
  assert.equal(p.backendDir, path.join(res, "backend"));
  assert.equal(p.frontendDistDir, path.join(res, "frontend"));
  assert.equal(p.frozenBackendExe, path.join(res, "backend", BACKEND_EXE_NAME));
});

test("appPaths(packaged) without resourcesPath fails loudly", () => {
  assert.throws(() => appPaths({ isPackaged: true }), /resourcesPath is required/);
});

test("assertBackendBuilt is a no-op in dev mode (null exe)", () => {
  assert.doesNotThrow(() => assertBackendBuilt(null));
});

test("assertBackendBuilt throws a reinstall hint when the frozen exe is missing", () => {
  const missing = path.join(os.tmpdir(), "dp-no-backend", "deadparrots-backend.exe");
  assert.throws(() => assertBackendBuilt(missing), /reinstall the app/);
});

test("assertBackendBuilt passes once the frozen exe exists", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dp-backend-"));
  const exe = path.join(dir, "deadparrots-backend.exe");
  fs.writeFileSync(exe, "MZ");
  assert.doesNotThrow(() => assertBackendBuilt(exe));
});
