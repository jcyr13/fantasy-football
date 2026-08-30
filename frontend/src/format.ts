// Small display helpers shared across screens. No domain math (ADR-0003) — just
// turning backend numbers into strings.

export function pts(n: number): string {
  return n.toFixed(1);
}

export function signedPts(n: number): string {
  const s = n.toFixed(1);
  return n > 0 ? `+${s}` : s;
}

/** A signed integer, e.g. a positional-rank trade edge: `+12`, `0`, `-6`. */
export function signedInt(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

/** A player's positional rank as printed, e.g. `QB4`, `WR12`. */
export function posRank(position: string, rank: number): string {
  return `${position}${rank}`;
}

export function pct(fraction: number): string {
  return `${(fraction * 100).toFixed(0)}%`;
}

/**
 * A percentile rank that is *already* on the 0–100 scale (team strength,
 * points-for percentile, the contend/rebuild thresholds) — printed as a plain
 * rank, not scaled again the way `pct` scales a 0–1 fraction.
 */
export function pctile(rank0to100: number): string {
  return rank0to100.toFixed(0);
}

/** `max_p_win` / `free_agent` → `max p win` / `free agent`. */
export function humanizeLabel(snake: string): string {
  return snake.replace(/_/g, " ");
}

/** A short absolute stamp for the freshness header, e.g. `Aug 29 14:03`. */
export function shortStamp(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A compact "how long ago" for the freshness header, from a seconds age. */
export function ageLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}
