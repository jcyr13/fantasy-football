import type { FreeAgentsResponse } from "../api";
import { fetchFreeAgents } from "../api";
import { Caveats } from "../components/Caveats";
import { Metric } from "../components/Metric";
import { ReasonList } from "../components/ReasonList";
import { posRank, pts, signedPts } from "../format";
import { usePoll } from "../usePoll";

// Waiver / Free Agents: the two ranked lists over the ticket #15 waiver layer.
// Rest-of-season is value-over-replacement for hold-and-start adds; This-week
// streamers is next-week ceiling for a current bye/injury hole. Each row carries
// its bench-need fit, own-bye note, and worth-the-priority verdict. The waiver
// priority readout spells out what a claim costs (drop to last, no FAAB), and
// the post-cutdown window flag rides alongside.

export function WaiverFA() {
  const state = usePoll<FreeAgentsResponse>(fetchFreeAgents, 0);

  if (state.kind === "loading") {
    return <p className="state-msg">Loading the waiver wire…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load Waiver / Free Agents: {state.message}
      </p>
    );
  }

  const fa = state.data;
  const prio = fa.waiver_priority;
  const win = fa.cutdown_window;

  return (
    <div>
      <div className="panel">
        <div className="metric-row" style={{ alignItems: "center" }}>
          <div>
            <h1>Waiver / Free Agents</h1>
            <div className="num faint">
              {fa.season} · Week {fa.week}
            </div>
          </div>
          {fa.hole_roles.length > 0 && (
            <div>
              <span className="faint">Open holes this week</span>{" "}
              {fa.hole_roles.map((r) => (
                <span key={r} className="pos-tag">
                  {r}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="panel-row">
        <div className="panel">
          <h2>Waiver priority</h2>
          <div className="metric-row">
            <Metric
              label="Current"
              value={`#${prio.current_priority} of ${prio.team_count}`}
            />
            <Metric label="On a successful claim, drops to" value={`#${prio.drops_to_on_claim}`} />
            <Metric label="Already last?" value={prio.is_last ? "yes" : "no"} />
          </div>
          <p className="num faint mt-6">{prio.note}</p>
        </div>
        <div className="panel">
          <h2>Post-cutdown window</h2>
          <div className="metric-row">
            <Metric label="Window" value={win.window_name} />
            <Metric
              label="State"
              value={win.is_open ? "open now" : win.is_upcoming ? `opens in ${win.days_until_open}d` : "closed"}
            />
            <Metric label="Dates" value={`${win.opens} → ${win.closes}`} />
          </div>
          <p className="num faint mt-6">{win.note}</p>
        </div>
      </div>

      <div className="panel">
        <h2>Rest-of-season value (hold &amp; start)</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Player</th>
              <th className="n">Pos rank</th>
              <th className="n">ROS proj</th>
              <th className="n">VOR</th>
              <th>Bench-need fit</th>
              <th>Own bye</th>
              <th>Worth the priority?</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {fa.rest_of_season.map((v) => (
              <tr key={v.player_id}>
                <td>
                  <span className="pos-tag">{v.position}</span> {v.name}
                </td>
                <td className="n">{posRank(v.position, v.positional_rank)}</td>
                <td className="n">{pts(v.ros_projected_points)}</td>
                <td className="n">{signedPts(v.value_over_replacement)}</td>
                <td>{v.need_fit}</td>
                <td>{v.own_bye}</td>
                <td>{v.priority_verdict}</td>
                <td className="wrap">
                  <ReasonList reasons={v.reasons} />
                </td>
              </tr>
            ))}
            {fa.rest_of_season.length === 0 && (
              <tr>
                <td colSpan={8} className="faint">
                  No rest-of-season adds surfaced.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>This-week streamers</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Player</th>
              <th>Hole</th>
              <th className="n">Next-wk ceiling</th>
              <th>Bench-need fit</th>
              <th>Worth the priority?</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {fa.streamers.map((s) => (
              <tr key={s.player_id}>
                <td>
                  <span className="pos-tag">{s.position}</span> {s.name}
                </td>
                <td>
                  <span className="pos-tag">{s.hole_role}</span>
                </td>
                <td className="n">{pts(s.next_week_ceiling)}</td>
                <td>{s.need_fit}</td>
                <td>{s.priority_verdict}</td>
                <td className="wrap">
                  <ReasonList reasons={s.reasons} />
                </td>
              </tr>
            ))}
            {fa.streamers.length === 0 && (
              <tr>
                <td colSpan={6} className="faint">
                  No streamers surfaced — no current bye/injury hole.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Caveats items={fa.caveats} />
    </div>
  );
}
