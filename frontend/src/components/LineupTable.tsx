import type { LineupSlotProjection } from "../api";
import { pts } from "../format";

// A dense per-slot lineup readout: slot, player, floor/proj/ceiling, with the
// backend's low-confidence and unresolved-identity flags surfaced inline.

export function LineupTable({ rows }: { rows: LineupSlotProjection[] }) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Slot</th>
          <th>Player</th>
          <th className="n">Floor</th>
          <th className="n">Proj</th>
          <th className="n">Ceil</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.slot}-${r.player_id}`}>
            <td>
              <span className="pos-tag">{r.slot || r.position}</span>
            </td>
            <td>
              {r.name}
              {r.low_confidence && (
                <span className="lowconf" title={r.reasons.join("; ") || "low confidence"}>
                  {" "}
                  ⚑
                </span>
              )}
              {!r.resolved && (
                <span className="unresolved" title="identity not resolved to nflverse; projection is a fallback">
                  {" "}
                  ?
                </span>
              )}
            </td>
            <td className="n">{pts(r.floor)}</td>
            <td className="n">{pts(r.mean)}</td>
            <td className="n">{pts(r.ceiling)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
