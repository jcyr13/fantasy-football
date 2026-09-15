import { useState } from "react";

import type { YahooPullResponse } from "../api";
import { importYahooPull, YAHOO_PAGES } from "../api";
import { requestRefresh } from "../refreshBus";
import { DoneSummary } from "./PullFromYahoo";

// "Import pull…" (issue #55): the fallback beside "Pull from Yahoo" for page
// payloads captured outside the app — a Claude in Chrome / Cowork session, or
// hand-saved JSON. John either pastes one JSON object keyed by page name or
// picks `matchup.json` / `players.json` / `injuries.json` / `standings.json`;
// either way the pages run through `POST /api/yahoo/import` and the result
// reads exactly like an assisted pull's. Payload shapes: docs/yahoo-import.md.

type ImportState =
  | { kind: "closed" }
  | { kind: "open"; error: string | null }
  | { kind: "importing" }
  | { kind: "done"; result: YahooPullResponse };

const PAGE_NAMES: readonly string[] = YAHOO_PAGES;

/** The pasted text as a page-keyed payload map, or a message saying why not. */
function parsePasted(text: string): Record<string, unknown> | string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return "Pasted text is not valid JSON.";
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return `Paste one JSON object keyed by page: ${YAHOO_PAGES.join(", ")}.`;
  }
  return parsed as Record<string, unknown>;
}

/** Picked files as a payload map keyed by filename stem (other files are
 * ignored); the text goes up as-is so a malformed file fails on its own page,
 * server-side. */
async function readPicked(files: FileList): Promise<Record<string, unknown> | string> {
  const payloads: Record<string, unknown> = {};
  for (const file of Array.from(files)) {
    const stem = file.name.replace(/\.json$/i, "");
    if (PAGE_NAMES.includes(stem)) {
      payloads[stem] = await file.text();
    }
  }
  if (Object.keys(payloads).length === 0) {
    return `No page files picked (expected ${YAHOO_PAGES.map((p) => `${p}.json`).join(", ")}).`;
  }
  return payloads;
}

export function ImportPull() {
  const [state, setState] = useState<ImportState>({ kind: "closed" });
  const [pasted, setPasted] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);

  async function submit() {
    const payloads =
      files && files.length > 0 ? await readPicked(files) : parsePasted(pasted);
    if (typeof payloads === "string") {
      setState({ kind: "open", error: payloads });
      return;
    }
    setState({ kind: "importing" });
    try {
      const result = await importYahooPull(payloads);
      setState({ kind: "done", result });
      setPasted("");
      setFiles(null);
      // Even a partial import changed data on the server.
      requestRefresh();
    } catch (err: unknown) {
      setState({
        kind: "open",
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const open = state.kind === "open" || state.kind === "importing";

  return (
    <span className="import-pull" role="status">
      <button
        type="button"
        className="pull-yahoo-btn"
        onClick={() => setState({ kind: "open", error: null })}
        disabled={open}
        data-testid="import-pull-button"
      >
        Import pull…
      </button>

      {state.kind === "done" && <DoneSummary result={state.result} />}

      {open && (
        <div
          className="import-pull-dialog"
          role="dialog"
          aria-label="Import Yahoo pull"
        >
          <label htmlFor="import-pull-paste">
            Paste a JSON object keyed by page ({YAHOO_PAGES.join(", ")}), or
            choose the page files (chosen files win over pasted text).
          </label>
          <textarea
            id="import-pull-paste"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            placeholder='{"matchup": {...}, "standings": {...}}'
            data-testid="import-pull-paste"
          />
          <input
            type="file"
            accept=".json,application/json"
            multiple
            onChange={(e) => setFiles(e.target.files)}
            data-testid="import-pull-files"
          />
          {state.kind === "open" && state.error && (
            <span
              className="pull-yahoo-msg pull-yahoo-msg--bad"
              data-testid="import-pull-error"
            >
              {state.error}
            </span>
          )}
          <span className="import-pull-actions">
            <button
              type="button"
              className="pull-yahoo-btn"
              onClick={submit}
              disabled={state.kind === "importing"}
              aria-busy={state.kind === "importing" || undefined}
              data-testid="import-pull-submit"
            >
              {state.kind === "importing" ? "Importing…" : "Import"}
            </button>
            <button
              type="button"
              className="pull-yahoo-btn"
              onClick={() => setState({ kind: "closed" })}
              disabled={state.kind === "importing"}
            >
              Cancel
            </button>
          </span>
        </div>
      )}
    </span>
  );
}
