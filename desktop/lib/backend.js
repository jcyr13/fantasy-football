"use strict";

const { spawn, spawnSync } = require("node:child_process");

// The command the shell uses to run the backend — the same one the README gives
// for a standalone run (`uv run uvicorn deadparrots.app:app`), with the loopback
// host and the chosen free port pinned. `DEADPARROTS_UV_BIN` overrides the `uv`
// executable for the case where it is not on Electron's PATH.
function buildBackendCommand({ port, host = "127.0.0.1" }) {
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
  onExit,
  onError,
}) {
  const { command, args } = buildBackendCommand({ port, host });
  const child = spawn(command, args, {
    cwd: backendDir,
    env: { ...process.env, DEADPARROTS_DATA_DIR: dataDir },
    stdio: "inherit",
    detached: process.platform !== "win32",
    windowsHide: true,
  });
  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      err = new Error(
        `could not launch the backend: "${command}" was not found on PATH. ` +
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

module.exports = { buildBackendCommand, waitForHealth, startBackend, stopBackend };
