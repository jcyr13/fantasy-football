"use strict";

const fs = require("node:fs/promises");
const { resolveStaticFile } = require("./static-files");
const { contentTypeFor } = require("./content-type");

// Request headers we never forward to the loopback backend: hop-by-hop headers
// and the fake `app://` host / length that fetch recomputes.
const DROP_REQUEST_HEADERS = new Set([
  "host",
  "connection",
  "content-length",
  "origin",
  "referer",
]);

// Response headers we strip before handing the payload to the renderer: Node's
// fetch has already decoded the body, so a lingering content-encoding would make
// Chromium try to decode it a second time.
const DROP_RESPONSE_HEADERS = new Set([
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
]);

function sanitized(headers, drop) {
  const out = new Headers();
  for (const [key, value] of headers) {
    if (!drop.has(key.toLowerCase())) out.set(key, value);
  }
  return out;
}

function textResponse(body, status) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

// The single handler behind the privileged `app://` scheme. Everything under
// `/api` is proxied to the backend so the SPA — whose API base is a hard-coded
// `/api` (frontend/src/api.ts) — talks to one same-origin host and needs no
// change. Everything else is a file from the built SPA in `distDir`.
function createRequestHandler({ distDir, backendOrigin }) {
  const origin = backendOrigin.replace(/\/$/, "");

  return async function handle(request) {
    const url = new URL(request.url);

    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      const init = {
        method: request.method,
        headers: sanitized(request.headers, DROP_REQUEST_HEADERS),
        redirect: "manual",
      };
      if (request.method !== "GET" && request.method !== "HEAD") {
        init.body = request.body;
        init.duplex = "half";
      }
      try {
        const upstream = await fetch(origin + url.pathname + url.search, init);
        return new Response(upstream.body, {
          status: upstream.status,
          statusText: upstream.statusText,
          headers: sanitized(upstream.headers, DROP_RESPONSE_HEADERS),
        });
      } catch (err) {
        return textResponse(`backend unreachable: ${err.message}`, 502);
      }
    }

    const file = resolveStaticFile(distDir, url.pathname);
    if (!file) return textResponse("not found", 404);
    const body = await fs.readFile(file);
    return new Response(body, { headers: { "content-type": contentTypeFor(file) } });
  };
}

module.exports = { createRequestHandler };
