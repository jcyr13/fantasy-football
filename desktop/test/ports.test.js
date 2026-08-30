"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");

const { pickFreePort } = require("../lib/ports");

function bind(port) {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on("error", reject);
    srv.listen(port, "127.0.0.1", () => resolve(srv));
  });
}

test("pickFreePort returns a usable high port", async () => {
  const port = await pickFreePort();
  assert.equal(typeof port, "number");
  assert.ok(Number.isInteger(port));
  assert.ok(port > 1023 && port < 65536, `port ${port} out of range`);

  const srv = await bind(port); // the port it handed back must be bindable
  await new Promise((r) => srv.close(r));
});

test("pickFreePort avoids a port already in use", async () => {
  const first = await pickFreePort();
  const held = await bind(first);
  try {
    const second = await pickFreePort();
    assert.notEqual(second, first);
  } finally {
    await new Promise((r) => held.close(r));
  }
});
