import { useEffect, useMemo, useRef, useState } from "react";

import type { LineupLabResult, LineupSlotProjection } from "../api";
import { computeLineupLab, fetchAutoFill } from "../api";
import { Metric } from "../components/Metric";
import { pct, pts } from "../format";
import { usePoll } from "../usePoll";

// Lineup Lab: drag players between Start / Bench / IR with a live backend
// recompute of total, floor, ceiling, and win probability after every move.
// Illegal lineups (wrong count, ineligible slot, a starter also on IR) are not
// blocked mid-drag — the numbers keep coming — but are clearly marked. The
// best-floor and best-ceiling auto-fills render side by side on demand and can
// be applied to the board.

type Zone = "start" | "bench" | "ir";
type Placement = Record<string, Zone>;

const ZONES: { id: Zone; label: string }[] = [
  { id: "start", label: "Start" },
  { id: "bench", label: "Bench" },
  { id: "ir", label: "IR" },
];

function idsIn(placement: Placement, zone: Zone): string[] {
  return Object.entries(placement)
    .filter(([, z]) => z === zone)
    .map(([id]) => id);
}

export function LineupLab() {
  const auto = usePoll(fetchAutoFill, 0);
  const [placement, setPlacement] = useState<Placement>({});
  const [result, setResult] = useState<LineupLabResult | null>(null);
  const [resultKey, setResultKey] = useState<string | null>(null);
  const [computing, setComputing] = useState(false);
  const [overZone, setOverZone] = useState<Zone | null>(null);
  const [showFills, setShowFills] = useState(false);

  const dragged = useRef<string | null>(null);
  const runId = useRef(0);

  const autoFill = auto.kind === "ready" ? auto.data : null;

  // Seed the board from the max-P(win) fill once the roster is in.
  useEffect(() => {
    if (!autoFill) return;
    const starters = new Set(autoFill.max_p_win);
    const next: Placement = {};
    for (const p of autoFill.roster) {
      next[p.player_id] = starters.has(p.player_id) ? "start" : "bench";
    }
    setPlacement(next);
  }, [autoFill]);

  const rosterById = useMemo(() => {
    const m = new Map<string, LineupSlotProjection>();
    for (const p of autoFill?.roster ?? []) m.set(p.player_id, p);
    return m;
  }, [autoFill]);

  const starterIds = useMemo(() => idsIn(placement, "start"), [placement]);
  const irIds = useMemo(() => idsIn(placement, "ir"), [placement]);
  const starterKey = starterIds.join(",");
  const irKey = irIds.join(",");
  const currentKey = `${starterKey}|${irKey}`;

  useEffect(() => {
    if (Object.keys(placement).length === 0) return;
    const id = ++runId.current;
    const dispatchedKey = currentKey;
    setComputing(true);
    computeLineupLab(starterIds, irIds)
      .then((r) => {
        if (id === runId.current) {
          setResult(r);
          setResultKey(dispatchedKey);
          setComputing(false);
        }
      })
      .catch(() => {
        if (id === runId.current) setComputing(false);
      });
    // starterKey / irKey are the stable joined form of the current id lists;
    // starterIds / irIds are read fresh inside the effect.
  }, [starterKey, irKey]);

  function moveTo(zone: Zone) {
    const id = dragged.current;
    dragged.current = null;
    setOverZone(null);
    if (!id) return;
    setPlacement((p) => (p[id] === zone ? p : { ...p, [id]: zone }));
  }

  function applyFill(ids: string[]) {
    const starters = new Set(ids);
    setPlacement((p) => {
      const next: Placement = {};
      for (const key of Object.keys(p)) {
        next[key] = starters.has(key) ? "start" : "bench";
      }
      return next;
    });
  }

  if (auto.kind === "error") {
    return (
      <p className="state-msg" role="alert">
        Could not load Lineup Lab: {auto.message}
      </p>
    );
  }
  if (!autoFill) {
    return <p className="state-msg">Loading roster…</p>;
  }

  // The shown result is for `resultKey`; if the board has moved since, it is
  // stale — dim it and drop the (now-outdated) illegal marking until the
  // recompute lands.
  const stale = result != null && resultKey !== currentKey;
  const illegal = result != null && !result.legal && !stale;

  return (
    <div>
      <div className="panel">
        <h2>Lineup Lab</h2>
        <p className="num faint" style={{ margin: 0 }}>
          Drag between Start / Bench / IR. The lineup is scored after every move.
        </p>
      </div>

      <div className="lab-board">
        {ZONES.map((z) => {
          const rows = idsIn(placement, z.id)
            .map((id) => rosterById.get(id))
            .filter((p): p is LineupSlotProjection => p != null);
          return (
            <div
              key={z.id}
              className={`lab-col${overZone === z.id ? " over" : ""}`}
              data-testid={`zone-${z.id}`}
              onDragOver={(e) => {
                e.preventDefault();
                if (overZone !== z.id) setOverZone(z.id);
              }}
              onDragLeave={() => setOverZone((cur) => (cur === z.id ? null : cur))}
              onDrop={() => moveTo(z.id)}
            >
              <h3>
                <span>{z.label}</span>
                <span className="num">
                  {z.id === "start" ? `${rows.length}/10` : rows.length}
                </span>
              </h3>
              <ul>
                {rows.map((p) => (
                  <li
                    key={p.player_id}
                    className="player-card"
                    draggable
                    data-testid={`player-${p.player_id}`}
                    onDragStart={(e) => {
                      dragged.current = p.player_id;
                      e.currentTarget.classList.add("dragging");
                      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
                    }}
                    onDragEnd={(e) => {
                      dragged.current = null;
                      e.currentTarget.classList.remove("dragging");
                    }}
                  >
                    <span className="pos-tag">{p.position}</span>
                    <span>{p.name}</span>
                    <span className="pmean">{pts(p.mean)}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <div
        className={`lab-result${illegal ? " illegal" : ""}${stale ? " stale" : ""}`}
      >
        {illegal && (
          <p className="illegal-banner" role="alert" data-testid="illegal-banner">
            ⚠ Illegal lineup — {result?.reason}
          </p>
        )}
        <Metric label="Total" value={<span data-testid="lab-total">{result ? pts(result.total) : "—"}</span>} />
        <Metric label="Floor" value={<span data-testid="lab-floor">{result ? pts(result.floor) : "—"}</span>} />
        <Metric label="Ceiling" value={<span data-testid="lab-ceiling">{result ? pts(result.ceiling) : "—"}</span>} />
        <Metric
          label="Win probability"
          value={<span data-testid="lab-winprob">{result ? pct(result.win_probability) : "—"}</span>}
        />
        {(computing || stale) && (
          <span className="computing" data-testid="lab-computing">
            recomputing…
          </span>
        )}
      </div>

      <div className="mt-12">
        <button className="linkish" onClick={() => setShowFills((s) => !s)}>
          {showFills ? "Hide" : "Show"} best-floor / best-ceiling auto-fill
        </button>
      </div>

      {showFills && (
        <div className="fills">
          <FillColumn
            title="Best-floor lineup"
            ids={autoFill.floor}
            rosterById={rosterById}
            onApply={() => applyFill(autoFill.floor)}
          />
          <FillColumn
            title="Best-ceiling lineup"
            ids={autoFill.ceiling}
            rosterById={rosterById}
            onApply={() => applyFill(autoFill.ceiling)}
          />
        </div>
      )}

      {autoFill.caveats.length > 0 && (
        <div className="panel mt-12">
          <h2>Methodology &amp; confidence</h2>
          <ul className="caveats">
            {autoFill.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FillColumn({
  title,
  ids,
  rosterById,
  onApply,
}: {
  title: string;
  ids: string[];
  rosterById: Map<string, LineupSlotProjection>;
  onApply: () => void;
}) {
  return (
    <div className="fill-col">
      <h3>
        <span>{title}</span>
        <button className="linkish" onClick={onApply}>
          Apply
        </button>
      </h3>
      <table className="tbl">
        <thead>
          <tr>
            <th>Player</th>
            <th className="n">Floor</th>
            <th className="n">Proj</th>
            <th className="n">Ceil</th>
          </tr>
        </thead>
        <tbody>
          {ids.map((id) => {
            const p = rosterById.get(id);
            return (
              <tr key={id}>
                <td>
                  {p ? (
                    <>
                      <span className="pos-tag">{p.position}</span> {p.name}
                    </>
                  ) : (
                    id
                  )}
                </td>
                <td className="n">{p ? pts(p.floor) : "—"}</td>
                <td className="n">{p ? pts(p.mean) : "—"}</td>
                <td className="n">{p ? pts(p.ceiling) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
