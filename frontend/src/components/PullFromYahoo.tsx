import { useState } from "react";

import type { YahooPullResponse } from "../api";
import {
  isExpiredYahooSession,
  triggerYahooPull,
  YahooPullUnavailableError,
} from "../api";
import { humanizeLabel } from "../format";
import { requestRefresh } from "../refreshBus";

// The "Pull from Yahoo" control that sits in the data-freshness strip (issue
// #46; ADR-0016 §3). One click runs `POST /api/yahoo/pull` against the desktop
// shell's signed-in Yahoo browser, then nudges every screen to refetch.
//
// Four outcomes are visible to John:
//  - in progress — the button says so and is disabled;
//  - success (whole or partial) — which pages landed, which failed, and the
//    waiver-priority "enter it by hand" reminder when the pull reports it;
//  - expired Yahoo session — a re-sign-in prompt plus a working retry (the
//    shell has already re-raised the Yahoo window; issue #45);
//  - no source wired (endpoint 503) — a short notice, button disabled.

type PullState =
  | { kind: "idle" }
  | { kind: "pulling" }
  | { kind: "done"; result: YahooPullResponse }
  | { kind: "expired" }
  | { kind: "error"; message: string }
  | { kind: "unavailable" };

function DoneSummary({ result }: { result: YahooPullResponse }) {
  const failed = result.pages.filter((p) => p.status === "failed");
  const ok = result.pages.filter((p) => p.status === "ok");
  return (
    <>
      <span className="pull-yahoo-msg" data-testid="pull-yahoo-status">
        {result.ok
          ? `Pulled all ${result.pages.length} pages`
          : `Pulled ${ok.length} of ${result.pages.length} — ${failed
              .map((p) => humanizeLabel(p.page))
              .join(", ")} failed`}
      </span>
      {failed.map((p) => (
        <span
          key={p.page}
          className="pull-yahoo-msg pull-yahoo-msg--bad"
          data-testid={`pull-yahoo-page-error-${p.page}`}
        >
          {humanizeLabel(p.page)}: {p.error ?? "unknown error"}
        </span>
      ))}
      {result.waiver_priority_needs_manual_entry && (
        <span className="reminder" data-testid="pull-yahoo-waiver-reminder">
          ⚠ waiver priority needs manual entry
        </span>
      )}
    </>
  );
}

export function PullFromYahoo() {
  const [state, setState] = useState<PullState>({ kind: "idle" });

  const busy = state.kind === "pulling";
  const disabled = busy || state.kind === "unavailable";

  async function pull() {
    setState({ kind: "pulling" });
    try {
      const result = await triggerYahooPull();
      if (isExpiredYahooSession(result.pages)) {
        setState({ kind: "expired" });
        return;
      }
      setState({ kind: "done", result });
      // Some data changed on the server — even a partial pull — so pull the
      // mounted screens forward.
      requestRefresh();
    } catch (err: unknown) {
      if (err instanceof YahooPullUnavailableError) {
        setState({ kind: "unavailable" });
        return;
      }
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const label =
    state.kind === "pulling"
      ? "Pulling from Yahoo…"
      : state.kind === "expired" || state.kind === "error"
        ? "Retry pull"
        : "Pull from Yahoo";

  return (
    <span className="pull-yahoo" role="status">
      <button
        type="button"
        className="pull-yahoo-btn"
        onClick={pull}
        disabled={disabled}
        aria-busy={busy || undefined}
        data-testid="pull-yahoo-button"
      >
        {label}
      </button>

      {state.kind === "done" && <DoneSummary result={state.result} />}

      {state.kind === "expired" && (
        <span className="reminder" data-testid="pull-yahoo-expired">
          ⚠ Yahoo session expired — sign in again in the Yahoo window, then
          retry.
        </span>
      )}

      {state.kind === "error" && (
        <span className="pull-yahoo-msg pull-yahoo-msg--bad">
          Pull failed — {state.message}
        </span>
      )}

      {state.kind === "unavailable" && (
        <span
          className="pull-yahoo-msg pull-yahoo-msg--faint"
          data-testid="pull-yahoo-unavailable"
        >
          Assisted pull needs the desktop app.
        </span>
      )}
    </span>
  );
}
