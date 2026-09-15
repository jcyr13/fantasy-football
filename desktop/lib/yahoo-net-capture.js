"use strict";

const fs = require("node:fs");
const path = require("node:path");

// Diagnostic network capture for the assisted pull (issue #56 spike). When
// DEADPARROTS_YAHOO_NET_DUMP_DIR is set, the Yahoo window attaches Chrome's
// DevTools protocol through Electron's `webContents.debugger` while a page
// loads and writes every JSON-ish response (URL, status, redacted request
// headers, body) to `<dir>/<page>/NNN.json`. The point is evidence for whether
// the pull can read the JSON Yahoo's own web app loads instead of the rendered
// DOM (docs/research/yahoo-json-capture.md). Off by default, and nothing here
// may fail a pull: every error degrades to "captured less".
//
// The debugger is injected, so this module is unit-tested against a fake; the
// Electron wiring stays in `./yahoo-window.js`.

const CDP_VERSION = "1.3";

// Resource types whose bodies are data rather than page furniture.
const DATA_RESOURCE_TYPES = new Set(["XHR", "Fetch"]);

// Header values that identify the session. The names stay, so the findings can
// still say "this request sends a crumb".
const SENSITIVE_HEADER = /cookie|authorization|crumb|token/i;

const CAPTURE_FILE = /^\d{3,}\.json$/;

function isCandidateResponse(response, resourceType) {
  const mimeType = (response && response.mimeType) || "";
  return /json/i.test(mimeType) || DATA_RESOURCE_TYPES.has(resourceType);
}

function redactHeaders(headers) {
  const out = {};
  for (const [name, value] of Object.entries(headers || {})) {
    out[name] = SENSITIVE_HEADER.test(name) ? "<redacted>" : value;
  }
  return out;
}

const NO_CAPTURE = Object.freeze({ stop: async () => ({ written: 0, failed: 0 }) });

// Start recording `page`'s responses into `<dir>/<page>/`. Resolves to a handle
// whose `stop()` waits for in-flight bodies, detaches (if it attached) and
// reports how many files it wrote and how many of those are error entries.
async function startNetCapture({ debugger: dbg, dir, page }) {
  if (!dir || !dbg) return NO_CAPTURE;

  const pageDir = path.join(dir, page);
  let attachedHere = false;
  try {
    clearPreviousCaptures(pageDir);
    if (!dbg.isAttached()) {
      dbg.attach(CDP_VERSION);
      attachedHere = true;
    }
    await dbg.sendCommand("Network.enable");
  } catch {
    if (attachedHere) safeDetach(dbg);
    return NO_CAPTURE;
  }

  const requests = new Map(); // requestId -> what we know about it so far
  const pending = new Set();
  let sequence = 0;
  let failed = 0;
  let stopped = false;

  function onMessage(_event, method, params) {
    if (stopped || !params) return;
    if (method === "Network.requestWillBeSent") {
      requests.set(params.requestId, {
        method: params.request && params.request.method,
        requestHeaders: redactHeaders(params.request && params.request.headers),
        resourceType: params.type,
      });
    } else if (method === "Network.responseReceived") {
      if (!isCandidateResponse(params.response, params.type)) {
        requests.delete(params.requestId);
        return;
      }
      const known = requests.get(params.requestId) || {};
      requests.set(params.requestId, {
        ...known,
        url: params.response.url,
        status: params.response.status,
        mimeType: params.response.mimeType,
        resourceType: params.type || known.resourceType,
        candidate: true,
      });
    } else if (method === "Network.loadingFinished") {
      const request = requests.get(params.requestId);
      requests.delete(params.requestId);
      if (!request || !request.candidate) return;
      const number = ++sequence;
      const job = record(params.requestId, request, number).finally(() => pending.delete(job));
      pending.add(job);
    }
  }

  async function record(requestId, request, number) {
    const { candidate, ...entry } = request;
    try {
      const { body, base64Encoded } = await dbg.sendCommand("Network.getResponseBody", { requestId });
      const text = base64Encoded ? Buffer.from(body, "base64").toString("utf8") : body;
      try {
        entry.body = JSON.parse(text);
        entry.bodyIsJson = true;
      } catch {
        entry.body = text;
        entry.bodyIsJson = false;
      }
    } catch (err) {
      entry.error = String((err && err.message) || err);
      failed += 1;
    }
    try {
      fs.mkdirSync(pageDir, { recursive: true });
      const name = `${String(number).padStart(3, "0")}.json`;
      fs.writeFileSync(path.join(pageDir, name), JSON.stringify(entry, null, 2), "utf8");
    } catch {
      /* diagnostic only */
    }
  }

  dbg.on("message", onMessage);

  async function stop() {
    if (stopped) return { written: sequence, failed };
    stopped = true;
    dbg.removeListener("message", onMessage);
    await Promise.allSettled([...pending]);
    if (attachedHere) safeDetach(dbg);
    return { written: sequence, failed };
  }

  return { stop };
}

function clearPreviousCaptures(pageDir) {
  if (!fs.existsSync(pageDir)) return;
  for (const name of fs.readdirSync(pageDir)) {
    if (CAPTURE_FILE.test(name)) fs.rmSync(path.join(pageDir, name), { force: true });
  }
}

function safeDetach(dbg) {
  try {
    dbg.detach();
  } catch {
    /* already gone */
  }
}

// The other non-DOM source the spike checks: bootstrap state the server
// embeds in the page (`window.__PRELOADED_STATE__`, `<script type=
// "application/json">` blobs and the like). Evaluated in the Yahoo page; returns
// the state-like globals and inline state scripts as plain JSON.
function buildBootstrapProbeScript() {
  return `(() => {
    const GLOBAL_NAME = /^__|state|preload|bootstrap|initial|config|context|^YAHOO/i;
    const STATE_SCRIPT = /__[A-Z_]+__\\s*=|preloaded|initial_?state|bootstrap/i;
    const serialize = (value) => {
      try {
        return JSON.parse(JSON.stringify(value));
      } catch (e) {
        return "<unserializable: " + String((e && e.message) || e) + ">";
      }
    };
    const globals = {};
    for (const name of Object.keys(window)) {
      if (!GLOBAL_NAME.test(name)) continue;
      let value;
      try {
        value = window[name];
      } catch {
        continue;
      }
      if (value === null || value === undefined || typeof value === "function") continue;
      if (typeof value === "object" && (value === window || value.nodeType)) continue;
      globals[name] = serialize(value);
    }
    const scripts = [];
    for (const el of document.querySelectorAll("script:not([src])")) {
      const text = el.textContent || "";
      if (/json/i.test(el.type || "") || STATE_SCRIPT.test(text)) {
        scripts.push({ id: el.id || null, type: el.type || null, length: text.length, text });
      }
    }
    return { url: location.href, globals, scripts };
  })()`;
}

module.exports = {
  startNetCapture,
  isCandidateResponse,
  redactHeaders,
  buildBootstrapProbeScript,
};
