"use strict";

// The Electron shell (docs/adr/0016 §1, issue #44 — Job 1).
//
// One window showing the working Dead Parrots Dashboard:
//   - pick a free loopback port;
//   - spawn the existing FastAPI backend on it (`uv run uvicorn ...`), with its
//     data directory pointed at the per-user app-data dir;
//   - serve the built SPA (frontend/dist) over a privileged `app://` scheme,
//     proxying `/api` to that backend so the SPA's hard-coded `/api` base needs
//     no change;
//   - tear the backend down when the window closes or the app quits.
//
// Nothing in backend/ or frontend/ changes; the backend still runs standalone
// under uvicorn exactly as before.

const fs = require("node:fs");
const path = require("node:path");
const { app, protocol, BrowserWindow, shell, dialog } = require("electron");

const { pickFreePort } = require("./lib/ports");
const { repoPaths, assertSpaBuilt } = require("./lib/paths");
const {
  startBackend,
  stopBackend,
  waitForHealth,
} = require("./lib/backend");
const { createRequestHandler } = require("./lib/request-handler");

const SCHEME = "app";
const HOST = "127.0.0.1";

let backendChild = null;
let shuttingDown = false;

// The `app://` scheme has to be registered as privileged before the app is
// ready: `standard` + `secure` so ES module scripts load, `supportFetchAPI` so
// the SPA's fetch() calls to `/api` work.
protocol.registerSchemesAsPrivileged([
  {
    scheme: SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      corsEnabled: true,
    },
  },
]);

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  stopBackend(backendChild);
  backendChild = null;
}

function fail(title, message) {
  console.error(`${title}: ${message}`);
  try {
    dialog.showErrorBox(title, message);
  } catch {
    /* dialog needs a ready app; the console line is the fallback */
  }
  shutdown();
  app.exit(1);
}

async function main() {
  const { backendDir, frontendDistDir } = repoPaths();
  try {
    assertSpaBuilt(frontendDistDir);
  } catch (err) {
    await app.whenReady().catch(() => {});
    fail("Dead Parrots Dashboard", err.message);
    return;
  }

  // The backend creates its own DB/cache files, but make the root itself so a
  // first launch has somewhere to write even if that ever changes.
  const dataDir = path.join(app.getPath("userData"), "data");
  fs.mkdirSync(dataDir, { recursive: true });

  const port = await pickFreePort(HOST);
  const backendOrigin = `http://${HOST}:${port}`;

  // Start the backend now so it boots while Electron finishes coming up.
  backendChild = startBackend({
    backendDir,
    port,
    dataDir,
    host: HOST,
    onError: (err) => {
      backendChild = null;
      if (!shuttingDown) fail("Dead Parrots Dashboard", err.message);
    },
    onExit: (code, signal) => {
      backendChild = null;
      if (!shuttingDown) {
        fail(
          "Dead Parrots Dashboard",
          `The backend process exited unexpectedly (code ${code}, signal ${signal}).`,
        );
      }
    },
  });

  await app.whenReady();

  protocol.handle(
    SCHEME,
    createRequestHandler({ distDir: frontendDistDir, backendOrigin }),
  );

  try {
    await waitForHealth(backendOrigin);
  } catch (err) {
    fail("Dead Parrots Dashboard", err.message);
    return;
  }

  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    title: "Dead Parrots Dashboard",
    backgroundColor: "#111111",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Links that target a new window (news-ticker sources open in a new tab) go to
  // the OS browser rather than a bare Electron window.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  await win.loadURL(`${SCHEME}://bundle/index.html`);
}

app.on("window-all-closed", () => {
  shutdown();
  app.quit();
});
app.on("before-quit", shutdown);
process.on("exit", shutdown);
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => {
    shutdown();
    process.exit(0);
  });
}

main().catch((err) => {
  fail("Dead Parrots Dashboard", err && err.stack ? err.stack : String(err));
});
