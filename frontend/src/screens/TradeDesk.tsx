import type { TradeCandidate, TradeDeskResponse } from "../api";
import { fetchTradeDesk } from "../api";
import { Caveats } from "../components/Caveats";
import { Metric } from "../components/Metric";
import { ReasonList } from "../components/ReasonList";
import { posRank, signedInt } from "../format";
import { usePoll } from "../usePoll";

// Trade Desk: buy-low / sell-high candidates over the ticket #15 trade layer.
// The market-value proxy is external consensus rest-of-season rank (there is no
// real trade market to observe); the model rank is opportunity-adjusted. Trade
// edge is the signed gap in positional-rank places — a candidate only surfaces
// when the edge clears roughly one positional tier in the flag's direction. The
// desperate-team read ranks the other 11 managers by willingness to deal. The
// countdown is to the November 28 trade deadline.

function CandidateTable({
  title,
  rows,
  edgeLabel,
}: {
  title: string;
  rows: TradeCandidate[];
  edgeLabel: string;
}) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      <table className="tbl">
        <thead>
          <tr>
            <th>Player</th>
            <th className="n">Market rank</th>
            <th className="n">Model rank</th>
            <th className="n">Edge</th>
            <th className="n">Priority</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.player_id}>
              <td>
                <span className="pos-tag">{c.position}</span> {c.name}
              </td>
              <td className="n">{posRank(c.position, c.market_rank)}</td>
              <td className="n">{posRank(c.position, c.model_rank)}</td>
              <td className="n">{signedInt(c.trade_edge)}</td>
              <td className="n">{c.priority.toFixed(2)}</td>
              <td className="wrap">
                <ReasonList reasons={c.reasons} />
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="faint">
                No {edgeLabel} candidates clear a full positional tier right now.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function TradeDesk() {
  const state = usePoll<TradeDeskResponse>(fetchTradeDesk, 0);

  if (state.kind === "loading") {
    return <p className="state-msg">Scanning the market…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load Trade Desk: {state.message}
      </p>
    );
  }

  const t = state.data;
  const cd = t.countdown;

  return (
    <div>
      <div className="panel">
        <div className="metric-row" style={{ alignItems: "center" }}>
          <div>
            <h1>Trade Desk</h1>
            <div className="num faint">
              {t.season} · Week {t.week}
            </div>
          </div>
          <span
            className={`badge badge--${cd.is_past ? "underdog" : "favored"}`}
          >
            {cd.is_past
              ? "TRADE DEADLINE PASSED"
              : `${cd.days_remaining} DAY${cd.days_remaining === 1 ? "" : "S"} TO DEADLINE`}
          </span>
          <Metric label="Deadline" value={cd.target_date} />
          <Metric label="As of" value={cd.as_of} />
        </div>
      </div>

      <CandidateTable title="Buy-low candidates" rows={t.buy_low} edgeLabel="buy-low" />
      <CandidateTable title="Sell-high candidates" rows={t.sell_high} edgeLabel="sell-high" />

      <div className="panel">
        <h2>Desperate-team read</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th className="n">#</th>
              <th>Team</th>
              <th className="n">Score</th>
              <th>Reasons</th>
            </tr>
          </thead>
          <tbody>
            {t.desperate_teams.map((d) => (
              <tr key={d.team_id}>
                <td className="n">{d.rank}</td>
                <td>{d.team_name}</td>
                <td className="n">{d.score.toFixed(2)}</td>
                <td className="wrap">
                  <ReasonList reasons={d.reasons} />
                </td>
              </tr>
            ))}
            {t.desperate_teams.length === 0 && (
              <tr>
                <td colSpan={4} className="faint">
                  No manager stands out as a likely dealer.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="num faint mt-6">
          Ranked by sub-.500 record, low points-for, roster age, and their own
          bye-week crunch — four equally-weighted, min-max-normalized components.
        </p>
      </div>

      <Caveats items={t.caveats} />
    </div>
  );
}
