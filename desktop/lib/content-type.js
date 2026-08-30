"use strict";

const path = require("node:path");

// Just enough of a MIME map to serve a Vite build: HTML, hashed JS/CSS, source
// maps, fonts and images. Anything unknown falls back to a binary download type.
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".txt": "text/plain; charset=utf-8",
};

function contentTypeFor(filePath) {
  return TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
}

module.exports = { contentTypeFor, TYPES };
