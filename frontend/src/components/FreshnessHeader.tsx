import { fetchFreshness } from "../api";
import { ageLabel, shortStamp } from "../format";
import { usePoll } from "../usePoll";

// The always-visible per-source status strip: last successful pull (absolute
// stamp), its age, and the current ok / failed / never state for each of
// nflverse, consensus, news, and Yahoo — plus the Yahoo staleness reminder and
// the manual waiver-priority flag when the backend reports them.

export function FreshnessHeader() {
  const state = usePoll(fetchFreshness, 60_000);

  if (state.kind !== "ready") {
    return (
      <div className="freshness">
        <span className="freshness-label">Data freshness</span>
        <span className="chip" data-state="never">
          <span className="dot" />
          <span className="src">
            {state.kind === "error" ? "freshness unreachable" : "loading…"}
          </span>
        </span>
      </div>
    );
  }

  const freshness = state.data;
  return (
    <div className="freshness">
      <span className="freshness-label">Data freshness</span>
      {freshness.sources.map((s) => (
        <span key={s.source} className="chip" data-state={s.state}>
          <span className="dot" />
          <span className="src">{s.source}</span>
          <span className="stamp">{shortStamp(s.last_success)}</span>
          {s.state !== "never" && (
            <span className="age">({ageLabel(s.age_seconds)})</span>
          )}
        </span>
      ))}
      {freshness.yahoo_reminder && (
        <span className="reminder">⚠ {freshness.yahoo_reminder}</span>
      )}
      {freshness.waiver_priority_needs_manual_entry && (
        <span className="reminder">⚠ waiver priority needs manual entry</span>
      )}
    </div>
  );
}
