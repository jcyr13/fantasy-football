"use strict";

const { spawn, spawnSync } = require("node:child_process");

const { DAMAGED_INSTALL_HINT } = require("./paths");

// The command the shell uses to run the backend, with the loopback host and the
// chosen free port pinned.
//
//   - packaged (`frozenBackendExe` given): the PyInstaller `--onedir` exe run
//     directly with `--host` / `--port` (issue #47; docs/adr/0016 §5). No `uv`,
//     no Python on the machine.
//   - development: the same standalone command `backend/README.md` gives,
//     `uv run uvicorn deadparrots.app:app`. `DEADPARROTS_UV_BIN` overrides the
//     `uv` executable for the case where it is not on Electron's PATH.
function buildBackendCommand({ port, host = "127.0.0.1", frozenBackendExe = null }) {
  if (frozenBackendExe) {
    return {
      command: frozenBackendExe,
      args: ["--host", host, "--port", String(port)],
    };
  }
  const uv = process.env.DEADPARROTS_UV_BIN || "uv";
  return {
    command: uv,
    args: [
      "run",
      "uvicorn",
      "deadparrots.app:app",
      "--host",
      host,
      "--port",
      String(port),
    ],
  };
}

// The environment the backend child runs with: the current env plus the
// per-user data directory and, when the shell has an embedded Yahoo browser
// running (issue #45 — Job 2), the loopback extractor endpoint that turns
// `POST /api/yahoo/pull` from a 503 into a real assisted pull. With
// `yahooExtractorUrl` omitted the var is left unset and the backend behaves
// exactly as a bare standalone run.
function buildBackendEnv({ dataDir, yahooExtractorUrl } = {}) {
  const env = { ...process.env };
  if (dataDir) env.DEADPARROTS_DATA_DIR = dataDir;
  if (yahooExtractorUrl) env.DEADPARROTS_YAHOO_EXTRACTOR_URL = yahooExtractorUrl;
  return env;
}

// Poll `GET /api/health` until it answers 2xx or the timeout elapses.
async function waitForHealth(origin, { timeoutMs = 30000, intervalMs = 300 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastErr = "no response";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(origin + "/api/health");
      if (res.ok) return true;
      lastErr = `HTTP ${res.status}`;
    } catch (err) {
      lastErr = err.message;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `backend at ${origin} was not healthy within ${timeoutMs}ms (last: ${lastErr})`,
  );
}

// Spawn the backend child, bound to `host:port`, with its data directory pointed
// at the per-user app-data dir. On POSIX it gets its own process group so the
// whole tree can be signalled on shutdown.
//
// `onExit(code, signal)` fires when the child ends. `onError(err)` fires when the
// spawn itself fails — most likely `uv` not on Electron's PATH (see
// `DEADPARROTS_UV_BIN`); without a listener that would be an unhandled event that
// crashes the main process.
function startBackend({
  backendDir,
  port,
  dataDir,
  host = "127.0.0.1",
  frozenBackendExe = null,
  yahooExtractorUrl,
  onExit,
  onError,
}) {
  const { command, args } = buildBackendCommand({ port, host, frozenBackendExe });
  const child = spawn(command, args, {
    cwd: backendDir,
    env: buildBackendEnv({ dataDir, yahooExtractorUrl }),
    stdio: "inherit",
    detached: process.platform !== "win32",
    windowsHide: true,
  });
  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      err = new Error(
        frozenBackendExe
          ? `could not launch the packaged backend at "${command}". ` +
            DAMAGED_INSTALL_HINT
          : `could not launch the backend: "${command}" was not found on PATH. ` +
            "Install uv, or set DEADPARROTS_UV_BIN to its full path.",
      );
    }
    if (onError) onError(err);
  });
  if (onExit) child.on("exit", onExit);
  return child;
}

// Terminate the backend child and every process it spawned (uv -> uvicorn ->
// the reloader/worker). Killing only `uv` would orphan the Python process.
function stopBackend(child) {
  if (!child || !child.pid) return;
  if (child.exitCode !== null || child.signalCode !== null) return;
  const pid = child.pid;
  try {
    if (process.platform === "win32") {
      // `taskkill /t` takes down the whole tree (uv -> uvicorn.exe -> python).
      // If it can't be resolved or spawned, fall back to a direct kill so the
      // child does not outlive the shell.
      const killed = spawnSync("taskkill", ["/pid", String(pid), "/t", "/f"], {
        stdio: "ignore",
      });
      if (killed.error || killed.status !== 0) child.kill();
    } else {
      process.kill(-pid, "SIGTERM");
      setTimeout(() => {
        try {
          process.kill(-pid, "SIGKILL");
        } catch {
          /* already gone */
        }
      }, 3000).unref();
    }
  } catch {
    /* already gone */
  }
}

module.exports = {
  buildBackendCommand,
  buildBackendEnv,
  waitForHealth,
  startBackend,
  stopBackend,
};
