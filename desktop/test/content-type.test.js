"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { contentTypeFor } = require("../lib/content-type");

test("contentTypeFor maps the file types a Vite build emits", () => {
  assert.equal(contentTypeFor("/x/index.html"), "text/html; charset=utf-8");
  assert.equal(contentTypeFor("assets/index-BHCEgCm_.js"), "text/javascript; charset=utf-8");
  assert.equal(contentTypeFor("assets/index-Da5yiWuK.css"), "text/css; charset=utf-8");
  assert.equal(contentTypeFor("logo.svg"), "image/svg+xml");
  assert.equal(contentTypeFor("font.woff2"), "font/woff2");
  assert.equal(contentTypeFor("index.js.map"), "application/json; charset=utf-8");
});

test("contentTypeFor is case-insensitive and falls back to octet-stream", () => {
  assert.equal(contentTypeFor("IMAGE.PNG"), "image/png");
  assert.equal(contentTypeFor("mystery.bin"), "application/octet-stream");
  assert.equal(contentTypeFor("noext"), "application/octet-stream");
});
