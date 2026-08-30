import type { ReactNode } from "react";

// The dense label-over-value cell used across This Week and Lineup Lab.

export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric">
      <span className="k">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}
