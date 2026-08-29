import { useState } from "react";

import type { RecommendationEngine, SideTotals, WeeklyView } from "../api";
import { fetchWeeklyView } from "../api";
import { LineupTable } from "../components/LineupTable";
import { Metric } from "../components/Metric";
import { humanizeLabel, pct, pts, signedPts } from "../format";
import { usePoll } from "../usePoll";

// This Week: the opponent and their likely lineup with the stated assumption,
// both projected totals (floor / projection / ceiling) with the Yahoo
// cross-check, favored / underdog + win %, the per-slot gap drivers, the
// opponent's swing players, and the recommended lineup with the floor, ceiling,
// and max-EV lineups shown alongside. The threshold-rule toggle re-queries the
// backend with `?engine=` — `usePoll` keeps the current view on screen while the
// swap is in flight, so the toggle changes the recommendation in place.

function Totals({ title, totals }: { title: string; totals: SideTotals }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <div className="metric-row">
        <Metric label="Floor" value={pts(totals.floor)} />
        <Metric label="Projection" value={pts(totals.projection)} />
        <Metric label="Ceiling" value={pts(totals.ceiling)} />
        <Metric label="Std dev" value={pts(totals.stdev)} />
        <Metric
          label="Yahoo proj"
          value={
            totals.yahoo_projected_total == null
              ? "—"
              : pts(totals.yahoo_projected_total)
          }
        />
      </div>
    </div>
  );
}

export function ThisWeek() {
  const [engine, setEngine] = useState<RecommendationEngine>("max-p-win");
  const state = usePoll<WeeklyView>(() => fetchWeeklyView(engine), 0, engine);

  if (state.kind === "loading") {
    return <p className="state-msg">Assembling this week…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load This Week: {state.message}
      </p>
    );
  }

  const weekly = state.data;
  const named = Object.fromEntries(weekly.named_lineups.map((n) => [n.label, n]));
  const order = ["max_p_win", "max_ev", "floor", "ceiling"] as const;

  return (
    <div>
      <div className="panel">
        <div className="metric-row" style={{ alignItems: "center" }}>
          <div>
            <h1>
              {weekly.dead_parrots_team} vs {weekly.opponent_team}
            </h1>
            <div className="num faint">
              {weekly.season} · Week {weekly.week} · as of {weekly.as_of_date} ·
              seed {weekly.rng_seed}
            </div>
          </div>
          <span
            className={`badge badge--${weekly.favored ? "favored" : "underdog"}`}
          >
            {weekly.favored ? "FAVORED" : "UNDERDOG"} · {pct(weekly.win_probability)}
          </span>
          <Metric label="Mean margin" value={signedPts(weekly.mean_margin)} />
        </div>
        <div className="metric-row mt-8" style={{ alignItems: "center" }}>
          <Metric
            label="Recommendation engine"
            value={
              <span className="engine-toggle">
                <button
                  aria-pressed={engine === "max-p-win"}
                  onClick={() => setEngine("max-p-win")}
                >
                  Max P(win)
                </button>
                <button
                  aria-pressed={engine === "threshold-rule"}
                  onClick={() => setEngine("threshold-rule")}
                >
                  Threshold rule
                </button>
              </span>
            }
          />
          <div className="num faint">
            active: {weekly.recommendation_engine}
            {state.refreshing ? " · updating…" : ""}
            {weekly.recommended_lineup_is_current
              ? " · matches the Yahoo-set lineup"
              : " · differs from the Yahoo-set lineup"}
          </div>
        </div>
      </div>

      <div className="panel-row">
        <Totals
          title={`${weekly.dead_parrots_team} — recommended`}
          totals={weekly.dead_parrots_totals}
        />
        <Totals
          title={`${weekly.opponent_team} — likely`}
          totals={weekly.opponent_totals}
        />
      </div>

      {weekly.dead_parrots_current_totals && (
        <div className="panel">
          <h3>Yahoo-set lineup as it stands</h3>
          <div className="metric-row">
            <Metric
              label="Floor / Proj / Ceil"
              value={`${pts(weekly.dead_parrots_current_totals.floor)} / ${pts(
                weekly.dead_parrots_current_totals.projection,
              )} / ${pts(weekly.dead_parrots_current_totals.ceiling)}`}
            />
            <Metric
              label="Win probability"
              value={
                weekly.current_win_probability == null
                  ? "—"
                  : pct(weekly.current_win_probability)
              }
            />
          </div>
        </div>
      )}

      <div className="panel-row">
        <div className="panel">
          <h2>Recommended lineup</h2>
          <LineupTable rows={weekly.recommended_lineup} />
        </div>
        <div className="panel">
          <h2>Opponent likely lineup</h2>
          <div className="num faint mt-6">
            assumption: {weekly.opponent_assumption}
          </div>
          {weekly.opponent_notes.length > 0 && (
            <ul className="caveats">
              {weekly.opponent_notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
          <LineupTable rows={weekly.opponent_likely_lineup} />
        </div>
      </div>

      <div className="panel">
        <h2>Lineups alongside</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Lineup</th>
              <th className="n">Win %</th>
              <th className="n">Exp pts</th>
              <th className="n">Floor</th>
              <th className="n">Ceiling</th>
            </tr>
          </thead>
          <tbody>
            {order
              .filter((label) => named[label])
              .map((label) => {
                const n = named[label];
                return (
                  <tr key={label}>
                    <td>{humanizeLabel(label)}</td>
                    <td className="n">{pct(n.win_probability)}</td>
                    <td className="n">{pts(n.expected_points)}</td>
                    <td className="n">{pts(n.floor)}</td>
                    <td className="n">{pts(n.ceiling)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
        <div className="num faint mt-6">
          threshold rule: {weekly.threshold_rule.branch} · situation P(win){" "}
          {pct(weekly.threshold_rule.situation_p_win)} · favored ≥{" "}
          {pct(weekly.threshold_rule.favored_threshold)} · underdog ≤{" "}
          {pct(weekly.threshold_rule.underdog_threshold)}
        </div>
      </div>

      <div className="panel-row">
        <div className="panel">
          <h2>Gap drivers</h2>
          <table className="tbl">
            <thead>
              <tr>
                <th>Slot</th>
                <th>{weekly.dead_parrots_team}</th>
                <th>{weekly.opponent_team}</th>
                <th className="n">Δ</th>
              </tr>
            </thead>
            <tbody>
              {weekly.gap_drivers.map((d, i) => (
                <tr key={`${d.slot}-${i}`}>
                  <td>
                    <span className="pos-tag">{d.slot}</span>
                  </td>
                  <td>
                    {d.dead_parrots_player}{" "}
                    <span className="num faint">{pts(d.dead_parrots_mean)}</span>
                  </td>
                  <td>
                    {d.opponent_player}{" "}
                    <span className="num faint">{pts(d.opponent_mean)}</span>
                  </td>
                  <td
                    className="n"
                    style={{
                      color: d.contribution >= 0 ? "var(--good)" : "var(--bad)",
                    }}
                  >
                    {signedPts(d.contribution)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Opponent swing players</h2>
          <table className="tbl">
            <thead>
              <tr>
                <th className="n">#</th>
                <th>Player</th>
                <th className="n">Variance share</th>
              </tr>
            </thead>
            <tbody>
              {weekly.swing_players.map((s) => (
                <tr key={s.player_id}>
                  <td className="n">{s.rank}</td>
                  <td>
                    {s.name} <span className="pos-tag">{s.position}</span>
                  </td>
                  <td className="n">{pct(s.variance_share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {weekly.caveats.length > 0 && (
        <div className="panel">
          <h2>Methodology &amp; confidence</h2>
          <ul className="caveats">
            {weekly.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
