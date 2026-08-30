// Small display helpers shared across screens. No domain math (ADR-0003) — just
// turning backend numbers into strings.

export function pts(n: number): string {
  return n.toFixed(1);
}

export function signedPts(n: number): string {
  const s = n.toFixed(1);
  return n > 0 ? `+${s}` : s;
}

export function pct(fraction: number): string {
  return `${(fraction * 100).toFixed(0)}%`;
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
