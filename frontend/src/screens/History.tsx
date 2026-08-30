import type { HistoryRecord, HistoryResponse } from "../api";
import { fetchHistory } from "../api";
import { Metric } from "../components/Metric";
import { pct, pts, shortStamp, signedPts } from "../format";
import { usePoll } from "../usePoll";

// History: every stored weekly snapshot for the season, newest week first, each
// as "what the model said" beside "what happened". The model side is the frozen
// `captured.weekly` payload (ADR-0014 §1); the outcome side is null until the
// week's games are backfilled. When it is present, the per-player projected /
// actual / delta table is shown, biggest miss first.

function ResultBadge({ result }: { result: string }) {
  const cls = result.toLowerCase() === "win" ? "favored" : "underdog";
  return <span className={`badge badge--${cls}`}>{result.toUpperCase()}</span>;
}

function SnapshotCard({ record }: { record: HistoryRecord }) {
  const w = record.captured.weekly;
  const outcome = record.outcome;
  const actualMargin = outcome
    ? outcome.dead_parrots_total - outcome.opponent_total
    : null;
  const actuals = outcome
    ? [...outcome.player_actuals].sort(
        (a, b) => Math.abs(b.delta) - Math.abs(a.delta),
      )
    : [];

  return (
    <div className="panel">
      <div className="metric-row" style={{ alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0 }}>
            Week {record.week} — {w.dead_parrots_team} vs {w.opponent_team}
          </h2>
          <div className="num faint">
            captured {shortStamp(record.created_at)} · seed {record.rng_seed}
          </div>
        </div>
      </div>

      <div className="panel-row mt-8">
        <div className="panel">
          <h3>Model said</h3>
          <div className="metric-row">
            <span
              className={`badge badge--${w.favored ? "favored" : "underdog"}`}
            >
              {w.favored ? "FAVORED" : "UNDERDOG"} · {pct(w.win_probability)}
            </span>
            <Metric
              label={`${w.dead_parrots_team} proj`}
              value={pts(w.dead_parrots_totals.projection)}
            />
            <Metric
              label={`${w.opponent_team} proj`}
              value={pts(w.opponent_totals.projection)}
            />
            <Metric label="Mean margin" value={signedPts(w.mean_margin)} />
          </div>
        </div>
        <div className="panel">
          <h3>What happened</h3>
          {outcome ? (
            <div className="metric-row">
              <ResultBadge result={outcome.result} />
              <Metric
                label={`${w.dead_parrots_team} actual`}
                value={pts(outcome.dead_parrots_total)}
              />
              <Metric
                label={`${w.opponent_team} actual`}
                value={pts(outcome.opponent_total)}
              />
              <Metric
                label="Actual margin"
                value={actualMargin == null ? "—" : signedPts(actualMargin)}
              />
              <Metric
                label="Backfilled"
                value={shortStamp(outcome.backfilled_at)}
              />
            </div>
          ) : (
            <p className="num faint">Awaiting outcome backfill.</p>
          )}
        </div>
      </div>

      {outcome && actuals.length > 0 && (
        <table className="tbl mt-8">
          <thead>
            <tr>
              <th>Player</th>
              <th className="n">Projected</th>
              <th className="n">Actual</th>
              <th className="n">Δ</th>
            </tr>
          </thead>
          <tbody>
            {actuals.map((p) => (
              <tr key={p.player_id}>
                <td>{p.name}</td>
                <td className="n">{pts(p.projected_points)}</td>
                <td className="n">{pts(p.actual_points)}</td>
                <td
                  className="n"
                  style={{ color: p.delta >= 0 ? "var(--good)" : "var(--bad)" }}
                >
                  {signedPts(p.delta)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function History() {
  const state = usePoll<HistoryResponse>(fetchHistory, 0);

  if (state.kind === "loading") {
    return <p className="state-msg">Loading past weeks…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load History: {state.message}
      </p>
    );
  }

  const history = state.data;

  return (
    <div>
      <div className="panel">
        <h1>History</h1>
        <div className="num faint">
          What the model said each week, and what happened.
        </div>
      </div>

      {history.snapshots.length === 0 ? (
        <p className="state-msg">
          No weekly snapshots captured yet — the first is taken Sunday late
          morning once the week assembles.
        </p>
      ) : (
        history.snapshots.map((record) => (
          <SnapshotCard key={record.snapshot_id} record={record} />
        ))
      )}
    </div>
  );
}
