"use strict";

const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

// A throwaway `frontend/dist` with an index.html and one hashed asset.
function fixtureDist() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dp-dist-"));
  fs.writeFileSync(
    path.join(dir, "index.html"),
    '<!doctype html><script type="module" src="/assets/app.js"></script><div id=root></div>',
  );
  fs.mkdirSync(path.join(dir, "assets"));
  fs.writeFileSync(path.join(dir, "assets", "app.js"), "export const x = 1;");
  return dir;
}

// A loopback HTTP server standing in for the backend. Returns its origin and a
// close() that resolves when it is shut.
async function fakeBackend(handler) {
  const server = http.createServer(handler);
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  return {
    origin: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((r) => server.close(r)),
  };
}

module.exports = { fixtureDist, fakeBackend };
