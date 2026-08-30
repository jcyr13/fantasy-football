"use strict";

const fs = require("node:fs");
const path = require("node:path");

// The dev shell runs against the repo checkout: `desktop/` sits beside
// `backend/` and `frontend/` at the repo root. (Job 4 / #47 adds the packaged
// layout; this only covers `npm start` from a source tree.)
function repoPaths(desktopDir = path.resolve(__dirname, "..")) {
  const repoRoot = path.resolve(desktopDir, "..");
  return {
    repoRoot,
    backendDir: path.join(repoRoot, "backend"),
    frontendDistDir: path.join(repoRoot, "frontend", "dist"),
  };
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

module.exports = { repoPaths, assertSpaBuilt };
