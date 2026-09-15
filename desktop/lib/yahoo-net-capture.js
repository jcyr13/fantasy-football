"use strict";

const fs = require("node:fs");
const path = require("node:path");

// Diagnostic network capture for the assisted pull (issue #56 spike). When
// DEADPARROTS_YAHOO_NET_DUMP_DIR is set, the Yahoo window attaches Chrome's
// DevTools protocol through Electron's `webContents.debugger` while a page
// loads and writes every JSON-ish response (URL, status, redacted request
// headers, request body, response body) to `<dir>/<page>/NNN.json`, plus the
// page's bootstrap state to `<dir>/<page>/bootstrap.<moment>.json`. The point
// is evidence for whether the pull can read the JSON Yahoo's own web app loads
// instead of the rendered DOM (docs/research/yahoo-json-capture.md). Off by
// default, and nothing here may fail a pull: every error degrades to "captured
// less".
//
// The debugger is injected, so this module is unit-tested against a fake; the
// Electron wiring stays in `./yahoo-window.js`.

const CDP_VERSION = "1.3";

// Resource types whose bodies are data rather than page furniture.
const DATA_RESOURCE_TYPES = new Set(["XHR", "Fetch"]);

// Header and query names whose values identify the session. The names stay, so
// the findings can still say "this request sends a crumb".
const SENSITIVE_HEADER = /cookie|authorization|crumb|token/i;
const SENSITIVE_QUERY = /crumb|token|auth|sig/i;
const REDACTED = "<redacted>";

// What a previous run of the same page left behind.
const CAPTURE_FILE = /^(\d{3,}|bootstrap\.[\w-]+)\.json$/;

// Long enough for a big players payload, short enough that one body Chrome
// never hands back can't stall the pull.
const DEFAULT_BODY_TIMEOUT_MS = 10_000;

function isCandidateResponse(response, resourceType) {
  const mimeType = (response && response.mimeType) || "";
  return /json/i.test(mimeType) || DATA_RESOURCE_TYPES.has(resourceType);
}

function redactHeaders(headers) {
  const out = {};
  for (const [name, value] of Object.entries(headers || {})) {
    out[name] = SENSITIVE_HEADER.test(name) ? REDACTED : value;
  }
  return out;
}

function redactUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  let changed = false;
  for (const name of [...parsed.searchParams.keys()]) {
    if (SENSITIVE_QUERY.test(name)) {
      parsed.searchParams.set(name, REDACTED);
      changed = true;
    }
  }
  return changed ? parsed.toString() : url;
}

const NO_CAPTURE = Object.freeze({
  stop: async () => ({ written: 0, failed: 0 }),
  dumpBootstrap: async () => {},
});

// Start recording `page`'s responses into `<dir>/<page>/`. Resolves to a handle:
// - `dumpBootstrap(webContents, moment)` writes the bootstrap probe's result;
// - `stop()` waits for in-flight bodies, detaches (if it attached) and reports
//   how many files it wrote and how many of those are error entries.
async function startNetCapture({ debugger: dbg, dir, page, bodyTimeoutMs = DEFAULT_BODY_TIMEOUT_MS }) {
  if (!dir || !dbg) return NO_CAPTURE;

  const pageDir = path.join(dir, page);

  async function dumpBootstrap(webContents, moment) {
    try {
      const probe = await webContents.executeJavaScript(buildBootstrapProbeScript());
      writeJson(path.join(pageDir, `bootstrap.${moment}.json`), probe);
    } catch {
      /* diagnostic only */
    }
  }

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
    // No network capture, but the bootstrap probe doesn't need the debugger.
    return { ...NO_CAPTURE, dumpBootstrap };
  }

  const requests = new Map(); // requestId -> what we know about it so far
  const candidates = new Set(); // requestIds whose response is worth a file
  const pending = new Set();
  let sequence = 0;
  let written = 0;
  let failed = 0;
  let stopped = false;

  const known = (requestId) => requests.get(requestId) || {};

  function onMessage(_event, method, params) {
    if (stopped || !params) return;
    const id = params.requestId;
    if (method === "Network.requestWillBeSent") {
      const request = params.request || {};
      requests.set(id, {
        ...known(id),
        url: redactUrl(request.url),
        method: request.method,
        requestHeaders: redactHeaders(request.headers),
        postData: request.postData,
        hasPostData: Boolean(request.hasPostData || request.postData),
        resourceType: params.type,
      });
    } else if (method === "Network.requestWillBeSentExtraInfo") {
      // The headers as sent on the wire, where cookies show up. May arrive
      // before or after requestWillBeSent.
      requests.set(id, { ...known(id), wireHeaders: redactHeaders(params.headers) });
    } else if (method === "Network.responseReceived") {
      if (!isCandidateResponse(params.response, params.type)) {
        requests.delete(id);
        candidates.delete(id);
        return;
      }
      const request = known(id);
      requests.set(id, {
        ...request,
        url: redactUrl(params.response.url),
        status: params.response.status,
        mimeType: params.response.mimeType,
        resourceType: params.type || request.resourceType,
      });
      candidates.add(id);
    } else if (method === "Network.loadingFinished") {
      const request = requests.get(id);
      const isCandidate = candidates.has(id);
      forget(id);
      if (request && isCandidate) track(record(id, request, ++sequence));
    } else if (method === "Network.loadingFailed") {
      const request = requests.get(id);
      forget(id);
      if (!request || !DATA_RESOURCE_TYPES.has(params.type || request.resourceType)) return;
      failed += 1;
      const entry = { ...withoutPostFlag(request), error: params.errorText || "loading failed" };
      if (params.canceled) entry.canceled = true;
      track(write(entry, ++sequence));
    }
  }

  function forget(id) {
    requests.delete(id);
    candidates.delete(id);
  }

  function track(promise) {
    const job = promise.finally(() => pending.delete(job));
    pending.add(job);
  }

  async function record(requestId, request, number) {
    const entry = withoutPostFlag(request);
    if (request.hasPostData && entry.postData === undefined) {
      try {
        const answer = await withTimeout(
          dbg.sendCommand("Network.getRequestPostData", { requestId }),
          bodyTimeoutMs,
        );
        entry.postData = answer.postData;
      } catch (err) {
        entry.postDataError = errorText(err);
      }
    }
    try {
      const { body, base64Encoded } = await withTimeout(
        dbg.sendCommand("Network.getResponseBody", { requestId }),
        bodyTimeoutMs,
      );
      const text = base64Encoded ? Buffer.from(body, "base64").toString("utf8") : body;
      try {
        entry.body = JSON.parse(text);
        entry.bodyIsJson = true;
      } catch {
        entry.body = text;
        entry.bodyIsJson = false;
      }
    } catch (err) {
      entry.error = errorText(err);
      failed += 1;
    }
    await write(entry, number);
  }

  async function write(entry, number) {
    const name = `${String(number).padStart(3, "0")}.json`;
    if (writeJson(path.join(pageDir, name), entry)) written += 1;
  }

  dbg.on("message", onMessage);

  async function stop() {
    if (!stopped) {
      stopped = true;
      dbg.removeListener("message", onMessage);
      await Promise.allSettled([...pending]);
      if (attachedHere) safeDetach(dbg);
    }
    return { written, failed };
  }

  return { stop, dumpBootstrap };
}

function withoutPostFlag({ hasPostData, ...entry }) {
  return entry;
}

function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function errorText(err) {
  return String((err && err.message) || err);
}

// Best-effort pretty JSON write; true if the file landed.
function writeJson(file, value) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(value, null, 2), "utf8");
    return true;
  } catch {
    return false;
  }
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
  redactUrl,
  buildBootstrapProbeScript,
};
