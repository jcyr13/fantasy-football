"use strict";

const fs = require("node:fs");
const path = require("node:path");

// The dev shell runs against the repo checkout: `desktop/` sits beside
// `backend/` and `frontend/` at the repo root.
function repoPaths(desktopDir = path.resolve(__dirname, "..")) {
  const repoRoot = path.resolve(desktopDir, "..");
  return {
    repoRoot,
    backendDir: path.join(repoRoot, "backend"),
    frontendDistDir: path.join(repoRoot, "frontend", "dist"),
  };
}

// The frozen backend's executable name inside the PyInstaller `--onedir` bundle
// (issue #47; docs/adr/0016 §5). Windows is the only packaged target.
const BACKEND_EXE_NAME = "deadparrots-backend.exe";

// Shared tail for the "we can't launch the packaged backend" errors — the same
// sentence in `assertBackendBuilt` here and in `startBackend`'s spawn-error
// handler (`lib/backend.js`), kept in one place so they stay in step.
const DAMAGED_INSTALL_HINT =
  "The installation looks damaged — reinstall the app.";

// Where the shell finds the backend and the built SPA, for the mode it is
// running in:
//
//   - development (`npm start` from the checkout): they sit in the repo tree
//     beside `desktop/`, and the backend runs via `uv run uvicorn`
//     (`frozenBackendExe: null`);
//   - packaged (the NSIS installer): `electron-builder.yml` has copied the
//     PyInstaller `--onedir` backend to `resources/backend/` and the SPA to
//     `resources/frontend/`, and there is no `uv` on the machine — the backend
//     is the frozen exe.
function appPaths({ isPackaged = false, resourcesPath, desktopDir } = {}) {
  if (isPackaged) {
    if (!resourcesPath) {
      throw new Error("appPaths: resourcesPath is required for a packaged app");
    }
    const backendDir = path.join(resourcesPath, "backend");
    return {
      backendDir,
      frontendDistDir: path.join(resourcesPath, "frontend"),
      frozenBackendExe: path.join(backendDir, BACKEND_EXE_NAME),
    };
  }
  const { backendDir, frontendDistDir } = repoPaths(desktopDir);
  return { backendDir, frontendDistDir, frozenBackendExe: null };
}

// The shell loads the already-built SPA; it does not build it. Fail early and
// loudly when the build is missing rather than showing a blank window.
function assertSpaBuilt(frontendDistDir) {
  const index = path.join(frontendDistDir, "index.html");
  if (!fs.existsSync(index)) {
    throw new Error(
      `SPA build not found at ${index}\n` +
        "Build it first:  npm --prefix ../frontend install && npm --prefix ../frontend run build",
    );
  }
}

// A packaged app that cannot find its frozen backend has a damaged install,
// nothing the user can fix by building — say so instead of letting the spawn
// fail later with a bare ENOENT.
function assertBackendBuilt(frozenBackendExe) {
  if (!frozenBackendExe) return;
  if (!fs.existsSync(frozenBackendExe)) {
    throw new Error(
      `Packaged backend not found at ${frozenBackendExe}\n` + DAMAGED_INSTALL_HINT,
    );
  }
}

module.exports = {
  repoPaths,
  appPaths,
  assertSpaBuilt,
  assertBackendBuilt,
  BACKEND_EXE_NAME,
  DAMAGED_INSTALL_HINT,
};
