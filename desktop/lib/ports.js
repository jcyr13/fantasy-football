"use strict";

const net = require("node:net");

// Ask the OS for a free TCP port on `host` by binding to port 0, reading the
// assigned port, then releasing it. The backend child binds it a moment later;
// the race window is tiny and acceptable for a single-user desktop app.
function pickFreePort(host = "127.0.0.1") {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, host, () => {
      const { port } = srv.address();
      srv.close((err) => (err ? reject(err) : resolve(port)));
    });
  });
}

module.exports = { pickFreePort };
