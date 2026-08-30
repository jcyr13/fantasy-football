"use strict";

const { BrowserWindow } = require("electron");

const {
  buildExtractionScript,
  isYahooLoginUrl,
  validateScrapePayload,
  ScrapeError,
  YahooAuthRequiredError,
} = require("./yahoo-extract");

// The embedded, persistently signed-in Yahoo browser (docs/adr/0016 §2, issue
// #45 — Job 2). A hidden `BrowserWindow` on the named `persist:yahoo` session
// partition: the owner signs in once, cookies live in the partition between
// launches, and the "Pull from Yahoo" flow only reopens it when Yahoo has
// expired the session.
//
// This is the browser boundary — not unit-tested. The pure parts it leans on
// (the login detector, the payload check, the injected script) live in
// `./yahoo-extract.js` and are covered there.

const YAHOO_HOME = "https://football.fantasysports.yahoo.com";

// The named session partition holding the signed-in Yahoo cookies (docs/adr/0016
// §2). Persists between launches, so John signs in once.
const YAHOO_PARTITION = "persist:yahoo";

// Yahoo Fantasy hydrates its tables client-side after the document load event
// that `loadURL` resolves on. Give the SPA a beat, then confirm `readyState`.
const SETTLE_AFTER_LOAD_MS = 1800;
const SETTLE_READYSTATE_TIMEOUT_MS = 8000;

function createYahooExtractor({ onAuthRequired = () => {} } = {}) {
  let win = null;
  let destroying = false;

  function ensureWindow() {
    if (win && !win.isDestroyed()) return win;
    destroying = false;
    win = new BrowserWindow({
      show: false,
      width: 1200,
      height: 900,
      title: "Yahoo Fantasy sign-in",
      autoHideMenuBar: true,
      webPreferences: {
        partition: YAHOO_PARTITION,
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    // The owner closing the sign-in window must not tear down the session: hide
    // it and keep the partition (and its cookies) alive.
    win.on("close", (event) => {
      if (destroying || !win) return;
      event.preventDefault();
      win.hide();
    });
    return win;
  }

  async function settle(target) {
    await new Promise((r) => setTimeout(r, SETTLE_AFTER_LOAD_MS));
    try {
      await target.webContents.executeJavaScript(
        `new Promise((res) => {
           const done = () => (document.readyState === "complete" ? res(true) : setTimeout(done, 100));
           done();
           setTimeout(() => res(false), ${SETTLE_READYSTATE_TIMEOUT_MS});
         })`,
        true,
      );
    } catch {
      /* best effort — the scrape script itself will report if the page is unusable */
    }
  }

  function raiseAuthRequired(page) {
    // A prompt hook that throws is the caller's bug; swallow it so it can't mask
    // the auth signal, which is the thing that has to reach the backend.
    try {
      onAuthRequired();
    } catch {
      /* ignore */
    }
    return new YahooAuthRequiredError(page);
  }

  // The `PageExtractor` the scrape server calls: navigate the Yahoo view to
  // `url`, let it settle, and read the payload out of the page.
  async function extract(page, url) {
    const target = ensureWindow();

    try {
      await target.webContents.loadURL(url);
    } catch (err) {
      const landed = safeUrl(target) || err.validatedURL || "";
      if (isYahooLoginUrl(landed)) throw raiseAuthRequired(page);
      throw new ScrapeError(`could not load the ${page} page (${url}): ${err.message}`);
    }

    await settle(target);

    if (isYahooLoginUrl(safeUrl(target))) throw raiseAuthRequired(page);

    let result;
    try {
      result = await target.webContents.executeJavaScript(buildExtractionScript(page), true);
    } catch (err) {
      throw new ScrapeError(`the extraction script failed on the ${page} page: ${err.message}`);
    }

    if (result && result.authRequired) throw raiseAuthRequired(page);
    if (!result || !result.ok) {
      const detail = [result && result.reason, result && result.via && `via ${result.via}`]
        .filter(Boolean)
        .join("; ");
      throw new ScrapeError(
        `no usable payload from the Yahoo ${page} page${detail ? ` (${detail})` : ""}`,
      );
    }

    return validateScrapePayload(page, result.payload);
  }

  // Bring the sign-in window to the front on the Yahoo home page. Used by the
  // `onAuthRequired` hook and, later, by Job 3's "sign in again" prompt.
  async function showSignIn() {
    const target = ensureWindow();
    const current = safeUrl(target);
    if (!current || isYahooLoginUrl(current)) {
      await target.webContents.loadURL(YAHOO_HOME).catch(() => {});
    }
    target.show();
    target.focus();
  }

  function destroy() {
    destroying = true;
    if (win && !win.isDestroyed()) win.destroy();
    win = null;
  }

  return { extract, showSignIn, destroy };
}

function safeUrl(target) {
  try {
    return target.webContents.getURL();
  } catch {
    return "";
  }
}

module.exports = { createYahooExtractor, YAHOO_HOME };
