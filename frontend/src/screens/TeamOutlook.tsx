import type { ByeCrunchWeek, TeamOutlookResponse } from "../api";
import { fetchTeamOutlook } from "../api";
import { Caveats } from "../components/Caveats";
import { Metric } from "../components/Metric";
import { ReasonList } from "../components/ReasonList";
import { pct, pctile, pts, signedPts } from "../format";
import { usePoll } from "../usePoll";

// Team Outlook: the strategic health read over the ticket #15 team-outlook
// layer. Team strength is decay-weighted points-for as a league percentile —
// deliberately not win/loss record. Expected vs actual wins exposes luck. The
// contend / rebuild / hold signal is advisory only: it states its inputs and
// recommends no specific move. The bye-week crunch map grades each future week
// where multiple starters are on bye at one position.

const GRADE_CLASS: Record<string, string> = {
  ok: "good",
  warn: "warn",
  critical: "bad",
};

function gradeClass(grade: string): string {
  return GRADE_CLASS[grade] ?? "warn";
}

function ByeCrunchRow({ w }: { w: ByeCrunchWeek }) {
  return (
    <tr>
      <td className="n">Week {w.week}</td>
      <td>
        <span style={{ color: `var(--${gradeClass(w.grade)})`, fontWeight: 650 }}>
          {w.grade.toUpperCase()}
        </span>
      </td>
      <td className="n">{w.max_at_one_position}</td>
      <td>{w.can_field_legal_lineup ? "yes" : "no"}</td>
      <td className="wrap">
        {w.per_position.length === 0 ? (
          <span className="faint">—</span>
        ) : (
          <ul className="reasons">
            {w.per_position.map((p) => (
              <li key={p.role}>
                <span className="pos-tag">{p.role}</span> {p.starters_on_bye} on bye
                {p.starter_names.length > 0 && ` — ${p.starter_names.join(", ")}`}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td className="wrap">
        <ReasonList reasons={w.reasons} />
      </td>
    </tr>
  );
}

export function TeamOutlook() {
  const state = usePoll<TeamOutlookResponse>(fetchTeamOutlook, 0);

  if (state.kind === "loading") {
    return <p className="state-msg">Reading the season so far…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load Team Outlook: {state.message}
      </p>
    );
  }

  const o = state.data;
  const ts = o.team_strength;
  const ew = o.expected_wins;
  const sig = o.signal;

  return (
    <div>
      <div className="panel">
        <h1>Team Outlook</h1>
        <div className="num faint">
          {o.season} · Week {o.week}
        </div>
      </div>

      <div className="panel-row">
        <div className="panel">
          <h2>Team strength</h2>
          <div className="metric-row">
            <Metric label="League percentile" value={pctile(ts.percentile)} />
            <Metric label="Rank" value={`#${ts.rank} of 12`} />
            <Metric
              label="Decay-weighted PF"
              value={pts(ts.decay_weighted_points_for)}
            />
            <Metric label="Weeks counted" value={ts.weeks_counted} />
          </div>
          <p className="num faint mt-6">
            The health signal — rolling points-for as a percentile against the
            other 11 teams, not the win/loss record.
          </p>
        </div>
        <div className="panel">
          <h2>Expected vs actual wins</h2>
          <div className="metric-row">
            <Metric label="Expected" value={pts(ew.expected_wins)} />
            <Metric label="Actual" value={pts(ew.actual_wins)} />
            <Metric
              label="Luck"
              value={
                <span
                  style={{
                    color: ew.luck >= 0 ? "var(--good)" : "var(--bad)",
                  }}
                >
                  {signedPts(ew.luck)}
                </span>
              }
            />
            <Metric label="Weeks counted" value={ew.weeks_counted} />
          </div>
          <p className="num faint mt-6">
            Expected wins: how many weeks these scores would have won against a
            randomly drawn opponent. Actual minus expected is luck.
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="metric-row" style={{ alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Contend / Rebuild / Hold</h2>
          <span className="badge badge--underdog">{sig.signal.toUpperCase()}</span>
          <Metric label="Playoff odds" value={pct(o.playoff_odds)} />
        </div>
        <div className="metric-row mt-8">
          <Metric
            label="Points-for percentile"
            value={pctile(sig.points_for_percentile)}
          />
          <Metric label="Playoff odds (signal input)" value={pct(sig.playoff_odds)} />
          <Metric
            label="Contend ≥"
            value={pctile(sig.contend_percentile_threshold)}
          />
          <Metric
            label="Rebuild ≤"
            value={pctile(sig.rebuild_percentile_threshold)}
          />
          <Metric label="Active since" value={`Week ${sig.signal_start_week}`} />
          <Metric
            label="Recommends a move?"
            value={sig.recommends_transaction ? "yes" : "advisory only"}
          />
        </div>
        {sig.rationale.length > 0 && (
          <ul className="caveats mt-6">
            {sig.rationale.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Bye-week crunch map</h2>
        {o.bye_crunch.length === 0 ? (
          <p className="num faint">
            No future week has multiple starters on bye at one position.
          </p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th className="n">Week</th>
                <th>Grade</th>
                <th className="n">Max at one pos</th>
                <th>Legal lineup?</th>
                <th>Per position</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {o.bye_crunch.map((w) => (
                <ByeCrunchRow key={w.week} w={w} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Caveats items={o.caveats} />
    </div>
  );
}
