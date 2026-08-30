"use strict";

const fs = require("node:fs");
const path = require("node:path");

// Map a URL pathname onto a real file inside `distDir`.
//
//   - "/"                -> distDir/index.html
//   - "/assets/x.js"     -> distDir/assets/x.js  (when it exists)
//   - "/this-week"       -> distDir/index.html   (SPA client route, no extension)
//   - "/../secrets"      -> null                 (path traversal, refused)
//   - "/missing.js"      -> null
//
// Returns an absolute path or null.
function resolveStaticFile(distDir, pathname) {
  const root = path.resolve(distDir);

  let rel;
  try {
    rel = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (rel === "" || rel === "/") rel = "/index.html";

  const abs = path.resolve(root, "." + rel);
  if (abs !== root && !abs.startsWith(root + path.sep)) return null;

  if (fs.existsSync(abs) && fs.statSync(abs).isFile()) return abs;

  // Extensionless path: treat it as a client-side route and serve the shell.
  if (!path.extname(rel)) {
    const index = path.join(root, "index.html");
    if (fs.existsSync(index)) return index;
  }
  return null;
}

module.exports = { resolveStaticFile };
